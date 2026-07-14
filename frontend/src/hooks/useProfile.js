import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { profileApi } from "../services/api";

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => profileApi.get().then((r) => r.data),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data) => profileApi.update(data).then((r) => r.data),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

// Upload a resume PDF and get back AI-parsed structured fields. We don't persist
// here — the user reviews/edits the parsed data, then saves via useUpdateProfile.
export function useImportResume() {
  return useMutation({
    mutationFn: (file) => profileApi.importResume(file).then((r) => r.data),
  });
}
