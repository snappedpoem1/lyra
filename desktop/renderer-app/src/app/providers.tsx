import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useMemo } from "react";
import { router } from "@/app/router";

export function AppProviders() {
  const queryClient = useMemo(() => new QueryClient(), []);
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
