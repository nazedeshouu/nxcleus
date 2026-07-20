import { useQuery } from "@tanstack/react-query";
import { api, type PublicConfig } from "../../api/client";
import { MOCK_FORCED } from "../../api/config";

const FALLBACK: PublicConfig = { sovereign: false, fallback_serving: false, profile: "demo", demo: true };

/** Feature flags for the UI (06). Degrades gracefully when the backend isn't up (mock builds). */
export function usePublicConfig() {
  const q = useQuery({
    queryKey: ["config", "public"],
    queryFn: api.publicConfig,
    enabled: !MOCK_FORCED,
    retry: 0,
  });
  return { config: q.data ?? FALLBACK, isLive: q.isSuccess };
}
