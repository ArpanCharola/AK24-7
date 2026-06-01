import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tailoredResumesApi } from "../services/api";

export function useTailoredResumes() {
  return useQuery({
    queryKey: ["tailored-resumes"],
    queryFn: async () => (await tailoredResumesApi.list()).data,
  });
}

export function useTailoredResume(id) {
  return useQuery({
    queryKey: ["tailored-resume", id],
    queryFn: async () => (await tailoredResumesApi.get(id)).data,
    enabled: !!id,
  });
}

function _invalidate(qc, id) {
  qc.invalidateQueries({ queryKey: ["tailored-resume", id] });
  qc.invalidateQueries({ queryKey: ["tailored-resumes"] });
}

export function useUpdateTailoredResume(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => tailoredResumesApi.update(id, body).then((r) => r.data),
    onSuccess: () => _invalidate(qc, id),
  });
}

export function useRetailorResume(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => tailoredResumesApi.retailor(id).then((r) => r.data),
    onSuccess: () => _invalidate(qc, id),
  });
}

export function useRegeneratePdf(id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => tailoredResumesApi.regeneratePdf(id).then((r) => r.data),
    onSuccess: () => _invalidate(qc, id),
  });
}

export function useQuickTailor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => tailoredResumesApi.quick(body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tailored-resumes"] }),
  });
}

export function useExtractJd() {
  return useMutation({
    mutationFn: (jobUrl) => tailoredResumesApi.extractJd(jobUrl).then((r) => r.data),
  });
}

export function useDeleteTailoredResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => tailoredResumesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tailored-resumes"] }),
  });
}
