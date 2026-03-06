import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";
import { UnifiedWorkspace } from "@/app/UnifiedWorkspace";

export function AppProviders() {
  const queryClient = useMemo(() => new QueryClient({
    defaultOptions: {
      queries: {
        retry: 0,
        staleTime: 15_000,
        refetchOnWindowFocus: false,
      },
    },
  }), []);
  return (
    <QueryClientProvider client={queryClient}>
      <UnifiedWorkspace />
    </QueryClientProvider>
  );
}
