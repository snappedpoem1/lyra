export const DEFAULT_API_BASE = "http://localhost:5000";

export function normalizeApiBase(value?: string | null): string {
  const input = (value ?? "").trim();
  if (!input) {
    return DEFAULT_API_BASE;
  }
  return input.replace(/\/+$/, "");
}

export function getEnvApiBase(): string {
  return normalizeApiBase(import.meta.env.VITE_LYRA_API_BASE);
}

export function getEnvApiToken(): string {
  return String(import.meta.env.VITE_LYRA_API_TOKEN ?? "").trim();
}

export function joinApiUrl(baseUrl: string, path: string): string {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizeApiBase(baseUrl)}${cleanPath}`;
}
