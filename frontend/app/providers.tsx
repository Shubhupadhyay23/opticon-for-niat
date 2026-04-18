"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "next-auth/react";
import { useState, createContext, useContext } from "react";

// --- Demo-mode billing stub ---
// When no real billing provider is available, we expose a context that
// mimics the FlowgladProvider API so useBilling() never crashes.
const DemoBillingContext = createContext({
  checkFeatureAccess: () => false,
  createCheckoutSession: async () => {},
  loaded: true,
});

export function useDemoBilling() {
  return useContext(DemoBillingContext);
}

function DemoBillingProvider({ children }: { children: React.ReactNode }) {
  return (
    <DemoBillingContext.Provider
      value={{
        checkFeatureAccess: () => false,
        createCheckoutSession: async () => {},
        loaded: true,
      }}
    >
      {children}
    </DemoBillingContext.Provider>
  );
}

// --- Conditionally use real or demo billing ---
let BillingWrapper: React.ComponentType<{ children: React.ReactNode }>;

try {
  // Only use FlowgladProvider if the module is configured (has API keys)
  if (process.env.NEXT_PUBLIC_FLOWGLAD_PUBLISHABLE_KEY) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { FlowgladProvider } = require("@flowglad/nextjs");
    BillingWrapper = FlowgladProvider;
  } else {
    BillingWrapper = DemoBillingProvider;
  }
} catch {
  BillingWrapper = DemoBillingProvider;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <BillingWrapper>{children}</BillingWrapper>
      </SessionProvider>
    </QueryClientProvider>
  );
}
