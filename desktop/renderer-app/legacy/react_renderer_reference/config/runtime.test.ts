import { describe, expect, it } from "vitest";
import { DEFAULT_API_BASE, joinApiUrl, normalizeApiBase } from "./runtime";

describe("runtime URL helpers", () => {
  it("normalizes empty base URL to default", () => {
    expect(normalizeApiBase("")).toBe(DEFAULT_API_BASE);
    expect(normalizeApiBase(undefined)).toBe(DEFAULT_API_BASE);
  });

  it("trims trailing slashes", () => {
    expect(normalizeApiBase("http://localhost:5000///")).toBe("http://localhost:5000");
  });

  it("joins base and path safely", () => {
    expect(joinApiUrl("http://localhost:5000/", "api/health")).toBe("http://localhost:5000/api/health");
    expect(joinApiUrl("http://localhost:5000", "/api/health")).toBe("http://localhost:5000/api/health");
  });
});
