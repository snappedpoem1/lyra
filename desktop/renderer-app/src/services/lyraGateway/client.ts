import type { ZodType } from "zod";
import { joinApiUrl } from "@/config/runtime";
import { useConnectivityStore } from "@/stores/connectivityStore";
import { useSettingsStore } from "@/stores/settingsStore";
import { ApiError } from "@/services/lyraGateway/types";

const DEFAULT_TIMEOUT_MS = 8000;

async function fetchWithTimeout(input: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

export function resolveApiUrl(path: string): string {
  return joinApiUrl(useSettingsStore.getState().apiBaseUrl, path);
}

export async function requestJson<T>(
  path: string,
  schema: ZodType<T>,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  retryCount = 1,
): Promise<T> {
  const settings = useSettingsStore.getState();
  const method = init?.method ?? "GET";
  const endpoint = resolveApiUrl(path);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  Object.assign(headers, init?.headers ?? {});
  if (settings.apiToken) {
    headers["Authorization"] = `Bearer ${settings.apiToken}`;
  }

  let attempt = 0;
  while (true) {
    attempt += 1;
    try {
      const response = await fetchWithTimeout(endpoint, { ...init, headers }, timeoutMs);
      const text = await response.text();
      const detail = text ? JSON.parse(text) : null;
      useConnectivityStore.getState().recordCall({
        endpoint,
        method,
        ok: response.ok,
        statusCode: response.status,
        timestamp: new Date().toISOString(),
        error: response.ok ? undefined : detail?.error ?? response.statusText,
      });
      if (!response.ok) {
        useConnectivityStore.getState().setDegraded(detail?.error ?? response.statusText, response.status);
        throw new ApiError(detail?.error ?? `${response.status} ${response.statusText}`, endpoint, response.status, detail);
      }
      const parsed = schema.parse(detail);
      if (path === "/api/health") {
        useConnectivityStore.getState().setLive(parsed as Record<string, unknown>);
      }
      return parsed;
    } catch (error) {
      if (attempt <= retryCount) {
        continue;
      }
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Unknown API error";
      useConnectivityStore.getState().recordCall({
        endpoint,
        method,
        ok: false,
        timestamp: new Date().toISOString(),
        error: message,
      });
      useConnectivityStore.getState().setDegraded(message, error instanceof ApiError ? error.statusCode : null);
      throw error;
    }
  }
}
