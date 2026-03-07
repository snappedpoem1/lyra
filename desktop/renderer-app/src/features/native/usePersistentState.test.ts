// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { readStoredValue, writeStoredValue } from "./usePersistentState";

describe("usePersistentState helpers", () => {
  it("returns the fallback when the key is missing", () => {
    expect(readStoredValue("lyra:test:missing", true)).toBe(true);
  });

  it("round-trips JSON values through localStorage", () => {
    writeStoredValue("lyra:test:volume", 0.64);
    expect(readStoredValue("lyra:test:volume", 0.82)).toBe(0.64);
  });

  it("falls back when the stored payload is malformed", () => {
    window.localStorage.setItem("lyra:test:bad", "{");
    expect(readStoredValue("lyra:test:bad", "fallback")).toBe("fallback");
  });
});
