import { useQuery } from "@tanstack/react-query";
import { authApi, type AuthSession } from "../../api/client";
import { MOCK_FORCED } from "../../api/config";

/** Session state for the platform shell. Backend /auth/me returns a synthetic dev session when
 * auth is disabled, so `needsLogin` only ever trips when a real login wall is configured. */
export function useAuth() {
  const q = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authApi.me,
    enabled: !MOCK_FORCED, // static mock builds have no backend — never wall
    retry: 0,
    staleTime: 60_000,
  });
  const status = (q.error as { status?: number } | null)?.status;
  return {
    session: (q.data ?? null) as AuthSession | null,
    needsLogin: status === 401, // auth enabled + no valid session
    settled: !q.isLoading,
  };
}
