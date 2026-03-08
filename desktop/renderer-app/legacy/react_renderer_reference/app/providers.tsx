import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useMemo } from "react";
import { lyraTheme } from "@/app/lyraTheme";
import { UnifiedWorkspace } from "@/app/UnifiedWorkspace";
import { useNativeNotifications } from "@/features/native/useNativeNotifications";

function NativeAffordances() {
  useNativeNotifications();
  return null;
}

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
    <MantineProvider theme={lyraTheme}>
      <QueryClientProvider client={queryClient}>
        <NativeAffordances />
        <UnifiedWorkspace />
      </QueryClientProvider>
    </MantineProvider>
  );
}
