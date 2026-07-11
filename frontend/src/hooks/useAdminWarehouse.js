import { useQuery } from "@tanstack/react-query";
import api from "../services/api";

const unwrap = (response) => response.data;

export function useAdminAnalytics(range = "today") {
  return useQuery({
    queryKey: ["admin-analytics", range],
    queryFn: () => api.get("/admin/analytics", { params: { range } }).then(unwrap),
    retry: 1,
  });
}

export function useAdminWarehouse(params) {
  return useQuery({
    queryKey: ["admin-warehouse", params],
    queryFn: () => api.get("/admin/jobs", { params }).then(unwrap),
    placeholderData: (previous) => previous,
    retry: 1,
  });
}

export function useAdminRuns() {
  return useQuery({
    queryKey: ["admin-aggregation-runs"],
    queryFn: () => api.get("/admin/aggregation/runs", { params: { limit: 20 } }).then(unwrap),
    retry: 1,
  });
}
