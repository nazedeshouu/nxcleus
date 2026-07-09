import { useSyncExternalStore } from "react";
import { DEMO_TOKEN_EVENT, hasDemoToken } from "./config";

function subscribe(cb: () => void) {
  window.addEventListener(DEMO_TOKEN_EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(DEMO_TOKEN_EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** Reactive presenter-unlock state: true once an X-Demo-Token is stored. */
export function useDemoToken(): boolean {
  return useSyncExternalStore(subscribe, hasDemoToken, () => false);
}
