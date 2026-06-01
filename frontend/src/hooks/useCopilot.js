import { useMutation, useQuery } from "@tanstack/react-query";
import { copilotApi } from "../services/api";

export function useCopilotHistory() {
  return useQuery({
    queryKey: ["copilot-history"],
    queryFn: async () => {
      try {
        return (await copilotApi.history()).data;
      } catch (err) {
        if (err?.response?.status === 404) return [];
        throw err;
      }
    },
    staleTime: 60_000,
  });
}

export function useCopilotChat() {
  return useMutation({
    mutationFn: (body) => copilotApi.chat(body).then((r) => r.data),
  });
}
