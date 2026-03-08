/// <reference types="vite/client" />

declare global {
  interface Window {
    lyraWindow?: {
      minimize?: () => void;
      maximize?: () => void;
      close?: () => void;
      platform?: string;
      appVersion?: string;
      onBootStatus?: (callback: (status: { phase: string; message: string; ready: boolean }) => void) => () => void;
    };
  }
}

export {};
