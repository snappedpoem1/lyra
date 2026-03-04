import { useConnectivityStore } from "@/stores/connectivityStore";

export function ConnectivityBadge() {
  const state = useConnectivityStore((store) => store.state);
  return <span className={`connectivity-badge is-${state.toLowerCase()}`}>{state}</span>;
}
