import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "../services/api";

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => dashboardApi.stats().then((r) => r.data),
    staleTime: 30_000,
  });
}
