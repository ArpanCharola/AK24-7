import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { jobSearchesApi } from "../services/api";

export function useJobSearches() {
  return useQuery({
    queryKey: ["job-searches"],
    queryFn: () => jobSearchesApi.list().then((r) => r.data),
  });
}

export function useCreateJobSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data) => jobSearchesApi.create(data).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["job-searches"] }),
  });
}

export function useUpdateJobSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }) => jobSearchesApi.update(id, data).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["job-searches"] }),
  });
}

export function useDeleteJobSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => jobSearchesApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["job-searches"] }),
  });
}

export function useRunJobSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => jobSearchesApi.run(id).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["job-searches"] }),
  });
}
