/// <reference types="vite/client" />

declare global {
  interface Window {
    lyraWindow?: {
      minimize?: () => void;
      maximize?: () => void;
      close?: () => void;
      platform?: string;
      appVersion?: string;
    };
  }
}

export {};
