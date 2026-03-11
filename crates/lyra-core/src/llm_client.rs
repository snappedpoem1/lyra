use rusqlite::Connection;
use serde_json::{json, Value};
use tracing::warn;

use crate::providers::{load_llm_config, load_provider_config, LlmConfig};

#[derive(Clone, Debug)]
pub struct LlmEndpointConfig {
    provider_kind: String,
    base_url: String,
    model: String,
    api_key: String,
}

impl LlmEndpointConfig {
    pub fn new(provider_kind: String, base_url: String, model: String, api_key: String) -> Self {
        Self {
            provider_kind,
            base_url,
            model,
            api_key,
        }
    }

    fn from_llm_config(config: LlmConfig) -> Option<Self> {
        if config.base_url.trim().is_empty() || config.model.trim().is_empty() {
            return None;
        }
        Some(Self::new(
            config.provider_kind,
            config.base_url,
            config.model,
            config.api_key,
        ))
    }
}

#[derive(Clone, Debug)]
pub struct LlmClient {
    primary: LlmEndpointConfig,
    fallback: Option<LlmEndpointConfig>,
}

impl LlmClient {
    pub fn from_connection(conn: &Connection) -> Option<Self> {
        let primary = LlmEndpointConfig::from_llm_config(load_llm_config(conn))?;
        let fallback = fallback_endpoint(conn, &primary.provider_kind);
        Some(Self::from_endpoints(primary, fallback))
    }

    pub fn from_endpoints(primary: LlmEndpointConfig, fallback: Option<LlmEndpointConfig>) -> Self {
        Self { primary, fallback }
    }

    pub fn chat_completion_text(
        &self,
        system_prompt: &str,
        user_prompt: &str,
        max_tokens: usize,
        temperature: f64,
    ) -> Option<String> {
        let messages = json!([
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]);
        self.chat_completion_messages(&messages, Some(max_tokens), temperature)
    }

    pub fn chat_completion_messages(
        &self,
        messages: &Value,
        max_tokens: Option<usize>,
        temperature: f64,
    ) -> Option<String> {
        let primary_result = send_chat_completion(&self.primary, messages, max_tokens, temperature);
        attempt_with_fallback(
            primary_result,
            &self.primary,
            self.fallback.as_ref(),
            messages,
            max_tokens,
            temperature,
        )
    }
}

fn fallback_endpoint(conn: &Connection, primary_provider_kind: &str) -> Option<LlmEndpointConfig> {
    let fallback_key = match primary_provider_kind {
        "groq" => "openrouter",
        "openrouter" => "groq",
        _ => return None,
    };
    let config = load_provider_config(conn, fallback_key)?;
    let base_url = config
        .get("base_url")
        .or_else(|| config.get("openrouter_base_url"))
        .or_else(|| config.get("groq_base_url"))
        .and_then(|v| v.as_str())
        .unwrap_or(match fallback_key {
            "openrouter" => "https://openrouter.ai/api/v1",
            "groq" => "https://api.groq.com/openai/v1",
            _ => "",
        })
        .trim()
        .to_string();
    let model = config
        .get("model")
        .or_else(|| config.get("cloud_model"))
        .or_else(|| config.get("openrouter_model"))
        .or_else(|| config.get("groq_model"))
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim()
        .to_string();
    let api_key = config
        .get("api_key")
        .or_else(|| config.get("token"))
        .or_else(|| config.get("openrouter_api_key"))
        .or_else(|| config.get("groq_api_key"))
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .trim()
        .to_string();
    if base_url.is_empty() || model.is_empty() || api_key.is_empty() {
        return None;
    }
    Some(LlmEndpointConfig::new(
        fallback_key.to_string(),
        base_url,
        model,
        api_key,
    ))
}

fn attempt_with_fallback(
    primary_result: Result<String, LlmClientError>,
    primary: &LlmEndpointConfig,
    fallback: Option<&LlmEndpointConfig>,
    messages: &Value,
    max_tokens: Option<usize>,
    temperature: f64,
) -> Option<String> {
    match primary_result {
        Ok(text) => Some(text),
        Err(err) => {
            if should_failover(&err) {
                if let Some(fallback_endpoint) = fallback {
                    warn!(
                        "llm-client: primary provider {} failed ({}), trying fallback {}",
                        primary.provider_kind, err, fallback_endpoint.provider_kind
                    );
                    return send_chat_completion(
                        fallback_endpoint,
                        messages,
                        max_tokens,
                        temperature,
                    )
                    .map_err(|fallback_err| {
                        warn!(
                            "llm-client: fallback provider {} failed: {}",
                            fallback_endpoint.provider_kind, fallback_err
                        );
                    })
                    .ok();
                }
            }
            None
        }
    }
}

fn send_chat_completion(
    endpoint: &LlmEndpointConfig,
    messages: &Value,
    max_tokens: Option<usize>,
    temperature: f64,
) -> Result<String, LlmClientError> {
    let chat_url = format!(
        "{}/chat/completions",
        endpoint.base_url.trim_end_matches('/')
    );
    let mut builder = ureq::post(&chat_url).set("Content-Type", "application/json");
    if !endpoint.api_key.is_empty() {
        builder = builder.set("Authorization", &format!("Bearer {}", endpoint.api_key));
    }
    let mut body = json!({
        "model": endpoint.model,
        "messages": messages,
        "temperature": temperature
    });
    if let Some(max_tokens) = max_tokens {
        body["max_tokens"] = json!(max_tokens);
    }
    let response = builder
        .send_json(body)
        .map_err(|error| LlmClientError::Ureq(Box::new(error)))?;
    let payload: serde_json::Value = response.into_json().map_err(LlmClientError::Io)?;
    let text = payload
        .get("choices")
        .and_then(|v| v.get(0))
        .and_then(|v| v.get("message"))
        .and_then(|v| v.get("content"))
        .and_then(|v| v.as_str())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or(LlmClientError::InvalidResponse)?;
    Ok(text.to_string())
}

fn should_failover(error: &LlmClientError) -> bool {
    match error {
        LlmClientError::Ureq(err) => match err.as_ref() {
            ureq::Error::Status(code, _) => matches!(code, 429 | 500 | 502 | 503 | 504),
            ureq::Error::Transport(_) => true,
        },
        LlmClientError::Io(_) | LlmClientError::InvalidResponse => false,
    }
}

#[derive(Debug)]
enum LlmClientError {
    Ureq(Box<ureq::Error>),
    Io(std::io::Error),
    InvalidResponse,
}

impl std::fmt::Display for LlmClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Ureq(err) => write!(f, "{err}"),
            Self::Io(err) => write!(f, "{err}"),
            Self::InvalidResponse => write!(f, "missing choices[0].message.content in response"),
        }
    }
}
