/** Base path is /api (06). VITE_API_BASE overrides host in dev; VITE_MOCK forces fixtures. */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "") + "/api";
export const MOCK_FORCED = import.meta.env.VITE_MOCK === "1";

const TOKEN_KEY = "nxcleus.demo_token";

export function getDemoToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export const DEMO_TOKEN_EVENT = "nx-demo-token";

export function setDemoToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
  // notify presenter-gated controls in the same tab (storage event only fires cross-tab)
  try {
    window.dispatchEvent(new CustomEvent(DEMO_TOKEN_EVENT));
  } catch {
    /* non-browser */
  }
}
export function hasDemoToken(): boolean {
  return !!getDemoToken();
}
