import { useSyncExternalStore } from "react";
import { DEMO_TOKEN_EVENT, hasDemoToken } from "./config";
import { useAuth } from "../components/shell/useAuth";

function subscribe(cb: () => void) {
  window.addEventListener(DEMO_TOKEN_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(DEMO_TOKEN_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/**
 * Reactive write-gate: true when the current user may perform demo writes. That's the case
 * once they hold a valid session — real login when auth is enabled, or the synthetic dev
 * session /auth/me returns when auth is off — or when a legacy X-Demo-Token is stored (the
 * hidden ?presenter= path). Cookie-session auth is now the primary gate; the demo token is
 * kept only as a fallback. The backend re-checks every write, so this only drives UI enablement.
 */
export function useDemoToken(): boolean {
  const hasToken = useSyncExternalStore(subscribe, hasDemoToken, () => false);
  const { session } = useAuth();
  return hasToken || !!session;
}
