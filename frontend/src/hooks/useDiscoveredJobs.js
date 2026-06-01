import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { discoveredJobsApi } from "../services/api";

export function useDiscoveredJobs(status, postedWithinDays) {
  return useQuery({
    queryKey: ["discovered-jobs", status, postedWithinDays],
    queryFn: () => discoveredJobsApi.list(status, postedWithinDays).then((r) => r.data),
    refetchInterval: 15000,
  });
}

export function useQueueJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => discoveredJobsApi.queue(id).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useBulkQueueJobs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids) => discoveredJobsApi.bulkQueue(ids).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useSkipJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => discoveredJobsApi.skip(id).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] }),
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => discoveredJobsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] }),
  });
}

export function useBulkDeleteJobs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids) => discoveredJobsApi.bulkDelete(ids),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] }),
  });
}

export function useFindContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, useApify = true }) =>
      discoveredJobsApi.findContact(id, useApify).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["discovered-jobs"] }),
  });
}
