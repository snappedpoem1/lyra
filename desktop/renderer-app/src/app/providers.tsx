import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useMemo } from "react";
import { router } from "@/app/router";

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
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
