import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applicationsApi } from "../services/api";

export function useApplications() {
  return useQuery({
    queryKey: ["applications"],
    queryFn: () => applicationsApi.list().then((r) => r.data),
    refetchInterval: 5000,
  });
}

export function useApply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data) => applicationsApi.apply(data).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
}

export function useRetryApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id) => applicationsApi.retry(id).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });
}

export function useSubmitOtp() {
  return useMutation({
    mutationFn: (data) => applicationsApi.submitOtp(data).then((r) => r.data),
  });
}
