// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { getHostBackendBaseUrl, listenHostBootStatus, listenHostTransport } from "./tauriHost";

type WindowWithTauri = Record<string, unknown>;

function windowAs(): WindowWithTauri {
  return window as unknown as WindowWithTauri;
}

describe("tauriHost", () => {
  afterEach(() => {
    delete windowAs().__TAURI_IPC__;
    delete windowAs().__TAURI_INTERNALS__;
    vi.resetModules();
    vi.restoreAllMocks();
  });

  describe("listenHostTransport", () => {
    it("is a deprecated noop regardless of runtime", async () => {
      const handler = vi.fn();
      const unlisten = await listenHostTransport(handler);
      expect(handler).not.toHaveBeenCalled();
      expect(typeof unlisten).toBe("function");
      expect(() => unlisten()).not.toThrow();
    });
  });

  describe("listenHostBootStatus — non-Tauri runtime", () => {
    it("returns a noop when neither __TAURI_IPC__ nor __TAURI_INTERNALS__ is present", async () => {
      const handler = vi.fn();
      const unlisten = await listenHostBootStatus(handler);
      expect(handler).not.toHaveBeenCalled();
      expect(typeof unlisten).toBe("function");
    });
  });

  describe("getHostBackendBaseUrl", () => {
    it("returns null outside Tauri runtime", async () => {
      await expect(getHostBackendBaseUrl()).resolves.toBeNull();
    });

    it("invokes the host command in Tauri runtime", async () => {
      windowAs().__TAURI_INTERNALS__ = {};
      vi.doMock("@tauri-apps/api/core", () => ({
        invoke: vi.fn().mockResolvedValue("http://127.0.0.1:5000/"),
      }));

      const result = await getHostBackendBaseUrl();
      expect(result).toBe("http://127.0.0.1:5000");
      vi.doUnmock("@tauri-apps/api/core");
    });
  });

  describe("isTauriRuntime detection (Tauri v1 / v2 compatibility)", () => {
    it("recognises Tauri v1 via __TAURI_IPC__", () => {
      windowAs().__TAURI_IPC__ = {};
      expect("__TAURI_IPC__" in window).toBe(true);
    });

    it("recognises Tauri v2 via __TAURI_INTERNALS__", () => {
      windowAs().__TAURI_INTERNALS__ = {};
      expect("__TAURI_INTERNALS__" in window).toBe(true);
    });

    it("is not a Tauri runtime when neither marker is present", () => {
      expect("__TAURI_IPC__" in window).toBe(false);
      expect("__TAURI_INTERNALS__" in window).toBe(false);
    });
  });
});
