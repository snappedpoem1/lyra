export class ApiError extends Error {
  statusCode?: number;
  endpoint: string;
  detail?: unknown;

  constructor(message: string, endpoint: string, statusCode?: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.endpoint = endpoint;
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export type ConnectionState = "LIVE" | "DEGRADED" | "FIXTURE";
