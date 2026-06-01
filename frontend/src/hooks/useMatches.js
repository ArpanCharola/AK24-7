import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { matchesApi } from "../services/api";

export function useMatches(filters = {}) {
  return useQuery({
    queryKey: ["matches", filters],
    // The matching backend is built in parallel — if /matches/feed isn't live yet
    // (404), surface an empty feed instead of an error screen so the page renders.
    queryFn: async () => {
      try {
        return (await matchesApi.feed(filters)).data;
      } catch (err) {
        if (err?.response?.status === 404) return [];
        throw err;
      }
    },
    refetchInterval: 30000,
  });
}

export function useRefreshMatches() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => matchesApi.refresh().then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["matches"] }),
  });
}
