import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { emailApi } from "../services/api";

export function useEmailStatus() {
  return useQuery({
    queryKey: ["email-status"],
    queryFn: () => emailApi.status().then((r) => r.data),
  });
}

export function useConnectEmail() {
  // Returns the Google consent URL; caller redirects the browser to it.
  return useMutation({
    mutationFn: () => emailApi.connect().then((r) => r.data.auth_url),
  });
}

export function useDisconnectEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => emailApi.disconnect().then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email-status"] }),
  });
}

export function useInbox({ limit = 100, pageToken, fresh = false } = {}) {
  return useQuery({
    queryKey: ["email-inbox", limit, pageToken, fresh],
    queryFn: () => emailApi.inbox({ limit, pageToken, fresh }).then((r) => r.data),
  });
}

export function useLabels(connected) {
  return useQuery({
    queryKey: ["email-labels"],
    queryFn: () => emailApi.labels().then((r) => r.data.labels),
    enabled: !!connected,
  });
}

export function useLabelMessages(labelId) {
  return useQuery({
    queryKey: ["email-label-messages", labelId],
    queryFn: () => emailApi.labelMessages(labelId).then((r) => r.data),
    enabled: !!labelId,
  });
}

export function useLabelSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => emailApi.syncLabels().then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-labels"] });
      qc.invalidateQueries({ queryKey: ["email-status"] });
    },
  });
}

export function useSetAutoLabel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled) => emailApi.setAutoLabel(enabled).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email-status"] }),
  });
}

export function useSetAutoFollowup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ enabled, afterDays }) => emailApi.setAutoFollowup(enabled, afterDays).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["email-status"] }),
  });
}

export function useComposeEmail() {
  return useMutation({ mutationFn: (body) => emailApi.compose(body).then((r) => r.data) });
}

export function useSendEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => emailApi.send(body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
}

export function useScanEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => emailApi.scan().then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["email-status"] });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}
