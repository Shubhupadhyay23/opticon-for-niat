"use client";

/**
 * Demo-safe useBilling hook.
 *
 * If Flowglad is configured (has publishable key), re-exports the real hook.
 * Otherwise returns a safe no-op stub so the app doesn't crash in demo mode.
 */

let _useBilling: () => {
  checkFeatureAccess: (slug: string) => boolean;
  createCheckoutSession: (opts: Record<string, unknown>) => Promise<void>;
  loaded: boolean;
};

try {
  if (process.env.NEXT_PUBLIC_FLOWGLAD_PUBLISHABLE_KEY) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const flowglad = require("@flowglad/nextjs");
    _useBilling = flowglad.useBilling;
  } else {
    _useBilling = () => ({
      checkFeatureAccess: () => true, // All features unlocked for Ollama/Local mode
      createCheckoutSession: async () => {},
      loaded: true,
    });
  }
} catch {
  _useBilling = () => ({
    checkFeatureAccess: () => false,
    createCheckoutSession: async () => {},
    loaded: true,
  });
}

export const useBilling = _useBilling;
