import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const PUBLIC_PATHS = ["/login", "/jobs"];

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const hadToken = !!localStorage.getItem("token");
      localStorage.removeItem("token");
      // Only bounce to /login if the user actually had a (now-invalid) token and
      // isn't already on a public page. Otherwise an authed-only call 401-ing on
      // the public /jobs page would kick out a legitimately-anonymous visitor.
      const onPublic = PUBLIC_PATHS.some((p) => window.location.pathname.startsWith(p));
      if (hadToken && !onPublic) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  // Returning-user login. `identifier` is email OR username.
  login: ({ identifier, password }) => api.post("/auth/login", { identifier, password }),
  // First-time setup right after Google sign-up: pick username + password.
  setupCredentials: ({ username, password }) =>
    api.post("/auth/setup-credentials", { username, password }),
  me: () => api.get("/auth/me"),
};

// Admin console — all endpoints require an is_admin token (backend 403s others).
export const adminApi = {
  listUsers: () => api.get("/admin/users"),
  getUser: (id) => api.get(`/admin/users/${id}`),
  deleteUser: (id) => api.delete(`/admin/users/${id}`),
  setActive: (id, isActive) => api.patch(`/admin/users/${id}`, { is_active: isActive }),
};

export const applicationsApi = {
  apply: (data) => api.post("/apply", data),
  retry: (id) => api.post(`/applications/${id}/retry`),
  getStatus: (jobId) => api.get(`/status/${jobId}`),
  list: () => api.get("/applications"),
  submitOtp: (data) => api.post("/otp/submit", data),
  getCoverLetter: (id) => api.get(`/applications/${id}/cover-letter`),
  regenerateCoverLetter: (id) => api.post(`/applications/${id}/cover-letter/regenerate`),
};

export const profileApi = {
  get: () => api.get("/profile"),
  update: (data) => api.put("/profile", data),
  uploadResume: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/profile/upload-resume", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  // Upload a resume and get back AI-parsed structured fields (contact, summary,
  // work experience, education, skills, projects, certifications) for the user to
  // review/edit before saving via update(). PLAN Phase 3b: POST /profile/import-resume.
  importResume: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/profile/import-resume", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  parsePdf: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/parse-pdf", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
};

export const jobSearchesApi = {
  list: () => api.get("/job-searches"),
  create: (data) => api.post("/job-searches", data),
  update: (id, data) => api.put(`/job-searches/${id}`, data),
  remove: (id) => api.delete(`/job-searches/${id}`),
  run: (id) => api.post(`/job-searches/${id}/run`),
};

// Resume-driven, AI-scored job matches (Jobright-style feed). The matching
// service (PLAN Phase 3 / contract #5) writes ranked matches per user; the feed
// returns DiscoveredJob-shaped rows enriched with match_score, match_explanation,
// missing_skills, salary_lpa, notice_period.
export const matchesApi = {
  feed: ({ location, minScore, postedWithinDays, sort = "score" } = {}) =>
    api.get("/matches/feed", {
      params: {
        ...(location ? { location } : {}),
        ...(minScore != null ? { min_score: minScore } : {}),
        ...(postedWithinDays ? { posted_within_days: postedWithinDays } : {}),
        sort,
      },
    }),
  refresh: () => api.post("/matches/refresh"),
};

// Orion — AI career copilot chat. body: { message, job_id?, history? }.
// Returns { reply, ... }. PLAN Phase 6: POST /copilot/chat.
export const copilotApi = {
  chat: (body) => api.post("/copilot/chat", body),
  history: () => api.get("/copilot/history"),
};

export const emailApi = {
  status: () => api.get("/email/status"),
  connect: () => api.get("/email/connect"), // returns { auth_url }
  disconnect: () => api.post("/email/disconnect"),
  scan: () => api.post("/email/scan"),
  inbox: ({ limit = 25, pageToken, label, fresh } = {}) =>
    api.get("/email/inbox", {
      params: { limit, page_token: pageToken, label, ...(fresh ? { fresh: true } : {}) },
    }),
  message: (id) => api.get(`/email/message/${encodeURIComponent(id)}`),
  labels: () => api.get("/email/labels"),
  labelMessages: (labelId, limit = 25) =>
    api.get(`/email/labels/${encodeURIComponent(labelId)}/messages`, { params: { limit } }),
  syncLabels: () => api.post("/email/labels/sync"),
  // Create a custom label. body: { name, nest_under?, purpose? }
  createLabel: (body) => api.post("/email/labels", body),
  compose: (body) => api.post("/email/compose", body),
  send: (body) => api.post("/email/send", body),
  setAutoLabel: (enabled) => api.post("/email/auto-label", { enabled }),
  setAutoFollowup: (enabled, after_days) => api.post("/email/auto-followup", { enabled, after_days }),
};

export const dashboardApi = {
  stats: () => api.get("/dashboard/stats"),
};

export const discoveredJobsApi = {
  list: (status, postedWithinDays) =>
    api.get("/discovered-jobs", {
      params: {
        ...(status ? { status } : {}),
        ...(postedWithinDays ? { posted_within_days: postedWithinDays } : {}),
      },
    }),
  queue: (id) => api.post(`/discovered-jobs/${id}/queue`),
  bulkQueue: (ids) => api.post("/discovered-jobs/bulk-queue", { ids }),
  skip: (id) => api.post(`/discovered-jobs/${id}/skip`),
  remove: (id) => api.delete(`/discovered-jobs/${id}`),
  bulkDelete: (ids) => api.post("/discovered-jobs/bulk-delete", { ids }),
  export: (status, postedWithinDays) =>
    api.get("/discovered-jobs/export", {
      params: {
        ...(status ? { status } : {}),
        ...(postedWithinDays ? { posted_within_days: postedWithinDays } : {}),
      },
      responseType: "blob",
    }),
  findContact: (id, useApify = false) =>
    api.post(`/discovered-jobs/${id}/find-contact`, null, {
      params: { use_apify: useApify },
    }),
};

// Public (unauthenticated) job pool — anyone can search/browse, only
// logged-in users can import results into a profile feed.
export const publicJobsApi = {
  search: ({ role, location = "India", source, postedWithinDays = 7, pages = 5 }) =>
    api.get("/public/job-search", {
      params: {
        role,
        location,
        ...(source ? { source } : {}),
        ...(postedWithinDays ? { posted_within_days: postedWithinDays } : {}),
        pages,
      },
    }),
  browse: ({ role, source, limit = 50, offset = 0 } = {}) =>
    api.get("/public/jobs", {
      params: {
        ...(role ? { role } : {}),
        ...(source ? { source } : {}),
        limit,
        offset,
      },
    }),
  importToProfile: (profileId, poolJobIds) =>
    api.post(`/public/import-to-profile/${profileId}`, { pool_job_ids: poolJobIds }),
};

export default api;
