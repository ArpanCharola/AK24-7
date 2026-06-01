import { useState } from "react";
import {
  useJobSearches,
  useCreateJobSearch,
  useUpdateJobSearch,
  useDeleteJobSearch,
  useRunJobSearch,
} from "../hooks/useJobSearches";

const EXPERIENCE_LEVELS = ["entry", "mid", "senior", "staff", "principal"];

const BLANK_FORM = {
  name: "",
  target_roles: "",
  locations: "",
  keywords: "",
  excluded_companies: "",
  experience_level: "",
  auto_apply_threshold: 75,
  auto_apply_mode: "review",
  is_active: true,
  work_arrangements: "",
  posted_within_days: "",
};

function FormField({ label, hint, children }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
        {label}
        {hint && <span className="ml-1.5 text-[10px] text-slate-400 font-normal normal-case tracking-normal">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

export default function JobPreferences() {
  const { data: profiles = [], isLoading } = useJobSearches();
  const { mutate: create, isPending: creating } = useCreateJobSearch();
  const { mutate: update, isPending: updating } = useUpdateJobSearch();
  const { mutate: remove } = useDeleteJobSearch();
  const { mutate: run } = useRunJobSearch();

  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK_FORM);
  const [runningId, setRunningId] = useState(null);
  const [toast, setToast] = useState(null);

  function showToast(type, message) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }

  function openNew() {
    setForm(BLANK_FORM);
    setEditing("new");
  }

  function openEdit(profile) {
    setForm({
      name: profile.name,
      target_roles: profile.target_roles || "",
      locations: profile.locations || "",
      keywords: profile.keywords || "",
      excluded_companies: profile.excluded_companies || "",
      experience_level: profile.experience_level || "",
      auto_apply_threshold: profile.auto_apply_threshold,
      auto_apply_mode: profile.auto_apply_mode || "review",
      is_active: profile.is_active,
      work_arrangements: profile.work_arrangements || "",
      posted_within_days: profile.posted_within_days ?? "",
    });
    setEditing(profile.id);
  }

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({ ...prev, [name]: type === "checkbox" ? checked : value }));
  }

  function toggleArrangement(opt) {
    const selected = (form.work_arrangements || "").split(",").map((s) => s.trim()).filter(Boolean);
    const next = selected.includes(opt) ? selected.filter((s) => s !== opt) : [...selected, opt];
    setForm((prev) => ({ ...prev, work_arrangements: next.join(",") }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const payload = {
      ...form,
      auto_apply_threshold: Number(form.auto_apply_threshold),
      posted_within_days: form.posted_within_days === "" ? null : Number(form.posted_within_days),
      work_arrangements: form.work_arrangements || null,
    };
    if (editing === "new") {
      create(payload, { onSuccess: () => setEditing(null) });
    } else {
      update({ id: editing, ...payload }, { onSuccess: () => setEditing(null) });
    }
  }

  function handleRun(id) {
    setRunningId(id);
    run(id, {
      onSuccess: () => {
        setRunningId(null);
        showToast("success", "Discovery started — check Discovered Jobs in a few minutes.");
      },
      onError: (err) => {
        setRunningId(null);
        showToast("error", err?.response?.data?.detail || err?.message || "Failed to start discovery");
      },
    });
  }

  const selectedArrangements = (form.work_arrangements || "").split(",").map((s) => s.trim()).filter(Boolean);

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-5 right-5 z-50 glass-strong rounded-2xl px-4 py-3 max-w-sm flex items-center gap-2.5 animate-slide-up`}>
          <span className={`w-2 h-2 rounded-full ${toast.type === "success" ? "bg-emerald-500" : "bg-rose-500"}`} />
          <p className="text-[13px] font-medium text-slate-800">{toast.message}</p>
        </div>
      )}

      {/* Header */}
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Search Profiles</h1>
            <p className="text-[13px] text-slate-500 mt-0.5">Define what roles to search for — runs automatically every 4 hours</p>
          </div>
          <button onClick={openNew} className="btn-primary">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Profile
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-4">
          {/* Inline form */}
          {editing !== null && (
            <div className="glass-strong rounded-2xl overflow-hidden animate-slide-up">
              <div className="px-6 py-4 border-b border-white/40">
                <h2 className="text-[15px] font-semibold text-slate-900 tracking-tight">
                  {editing === "new" ? "New Search Profile" : "Edit Profile"}
                </h2>
              </div>
              <form onSubmit={handleSubmit} className="p-6 space-y-5">
                <FormField label="Profile Name">
                  <input name="name" required value={form.name} onChange={handleChange}
                    placeholder="e.g. Senior ML Engineer" className="input-glass" />
                </FormField>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <FormField label="Target Roles" hint="comma-separated">
                    <input name="target_roles" value={form.target_roles} onChange={handleChange}
                      placeholder="ML Engineer, AI Engineer" className="input-glass" />
                  </FormField>
                  <FormField label="Keywords" hint="comma-separated">
                    <input name="keywords" value={form.keywords} onChange={handleChange}
                      placeholder="Python, PyTorch, LLM" className="input-glass" />
                  </FormField>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <FormField label="Locations" hint='or "Remote"'>
                    <input name="locations" value={form.locations} onChange={handleChange}
                      placeholder="San Francisco CA, Remote" className="input-glass" />
                  </FormField>
                  <FormField label="Excluded Companies" hint="comma-separated">
                    <input name="excluded_companies" value={form.excluded_companies} onChange={handleChange}
                      placeholder="Company A, Company B" className="input-glass" />
                  </FormField>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <FormField label="Experience Level">
                    <select name="experience_level" value={form.experience_level} onChange={handleChange} className="input-glass cursor-pointer">
                      <option value="">Any level</option>
                      {EXPERIENCE_LEVELS.map((l) => (
                        <option key={l} value={l}>{l.charAt(0).toUpperCase() + l.slice(1)}</option>
                      ))}
                    </select>
                  </FormField>
                  <FormField label="Posted Within" hint="days, blank = any">
                    <input type="number" name="posted_within_days" min="1" max="90"
                      value={form.posted_within_days} onChange={handleChange}
                      placeholder="e.g. 14" className="input-glass" />
                  </FormField>
                </div>

                <FormField label="Work Arrangement" hint="leave blank for any">
                  <div className="flex gap-2 mt-1">
                    {["remote", "hybrid", "onsite"].map((opt) => {
                      const active = selectedArrangements.includes(opt);
                      return (
                        <button
                          key={opt}
                          type="button"
                          onClick={() => toggleArrangement(opt)}
                          className={`relative px-4 py-1.5 text-[12.5px] font-semibold rounded-xl transition-all capitalize ${
                            active ? "text-white" : "text-slate-600 hover:text-slate-900 hover:bg-white/65"
                          }`}
                          style={
                            active
                              ? {
                                  background: "hsl(var(--primary))",
                                  boxShadow: "0 4px 14px -4px rgba(107,61,245,0.45)",
                                }
                              : {
                                  background: "rgba(255,255,255,0.55)",
                                  border: "1px solid rgba(15,23,42,0.08)",
                                }
                          }
                        >
                          {opt}
                        </button>
                      );
                    })}
                  </div>
                </FormField>

                {/* Auto-apply threshold */}
                <FormField label={
                  <span>
                    Auto-Apply Threshold
                    <span className="ml-2 text-accent-600 font-bold normal-case tracking-normal">{form.auto_apply_threshold}</span>
                  </span>
                } hint="auto-apply jobs scoring ≥ this">
                  <input type="range" name="auto_apply_threshold" min="0" max="100"
                    value={form.auto_apply_threshold} onChange={handleChange}
                    className="w-full accent-accent-600 mt-1" />
                  <div className="flex justify-between text-[10.5px] text-slate-400 font-medium mt-1.5">
                    <span>0 — apply to everything</span>
                    <span>100 — never auto-apply</span>
                  </div>
                </FormField>

                {/* Auto-apply mode */}
                <FormField label="When a job clears the threshold" hint="account-level auto-apply must also be ON in Profile">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                    {[
                      { value: "review", title: "Review-first", subtitle: "Park as auto-queued — one-click approve" },
                      { value: "auto",   title: "Fully auto",   subtitle: "Apply immediately (gated by daily cap)" },
                    ].map((opt) => {
                      const active = form.auto_apply_mode === opt.value;
                      return (
                        <button
                          key={opt.value}
                          type="button"
                          onClick={() => setForm((p) => ({ ...p, auto_apply_mode: opt.value }))}
                          className={`text-left rounded-xl p-3 transition-all ${
                            active
                              ? "ring-2 ring-accent-500 bg-white/80"
                              : "bg-white/55 border border-slate-200/60 hover:bg-white/70"
                          }`}
                        >
                          <div className={`text-[12.5px] font-semibold ${active ? "text-accent-700" : "text-slate-700"}`}>
                            {opt.title}
                          </div>
                          <div className="text-[11px] text-slate-500 mt-0.5">{opt.subtitle}</div>
                        </button>
                      );
                    })}
                  </div>
                </FormField>

                {/* Active toggle */}
                <label className="flex items-center gap-3 cursor-pointer select-none">
                  <div className="relative">
                    <input type="checkbox" name="is_active" checked={form.is_active}
                           onChange={handleChange} className="sr-only peer" />
                    <div className="w-11 h-6 bg-slate-200/70 rounded-full peer-checked:bg-accent-500 transition-colors shadow-inner-soft" />
                    <div className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-all peer-checked:translate-x-5" />
                  </div>
                  <span className="text-[13px] font-medium text-slate-700">
                    Active <span className="font-normal text-slate-400">(runs every 4 hours)</span>
                  </span>
                </label>

                <div className="flex gap-2.5 pt-2">
                  <button type="submit" disabled={creating || updating} className="btn-primary">
                    {creating || updating ? "Saving…" : "Save Profile"}
                  </button>
                  <button type="button" onClick={() => setEditing(null)} className="btn-secondary">
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Profile list */}
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2].map((i) => <div key={i} className="h-28 glass-subtle rounded-2xl animate-pulse" />)}
            </div>
          ) : profiles.length === 0 ? (
            <div className="glass-subtle rounded-2xl p-14 text-center">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                   style={{ background: "hsl(var(--muted))" }}>
                <svg className="w-7 h-7 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                </svg>
              </div>
              <p className="text-slate-800 font-semibold text-sm">No search profiles yet</p>
              <p className="text-slate-400 text-[12.5px] mt-1 mb-5">Create a profile to start discovering jobs automatically</p>
              <button onClick={openNew} className="btn-primary">
                Create your first profile
              </button>
            </div>
          ) : (
            <ul className="space-y-3">
              {profiles.map((profile) => (
                <li key={profile.id} className="glass-subtle rounded-2xl overflow-hidden transition-all hover:bg-white/65">
                  <div className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2.5 mb-2">
                          <h3 className="text-[14.5px] font-semibold text-slate-900 truncate tracking-tight">{profile.name}</h3>
                          <span className={`pill border ${
                            profile.is_active
                              ? "bg-emerald-100/80 text-emerald-700 border-emerald-200/60"
                              : "bg-slate-100/80 text-slate-500 border-slate-200/60"
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${profile.is_active ? "bg-emerald-500" : "bg-slate-400"}`} />
                            {profile.is_active ? "Active" : "Paused"}
                          </span>
                        </div>

                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          {profile.target_roles && (
                            <span className="text-[11.5px] text-slate-500">
                              <span className="font-semibold text-slate-700">Roles:</span> {profile.target_roles}
                            </span>
                          )}
                          {profile.keywords && (
                            <span className="text-[11.5px] text-slate-500">
                              <span className="font-semibold text-slate-700">Keywords:</span> {profile.keywords}
                            </span>
                          )}
                          {profile.locations && (
                            <span className="text-[11.5px] text-slate-500">
                              <span className="font-semibold text-slate-700">Locations:</span> {profile.locations}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-3 mt-2">
                          <span className="text-[11px] text-slate-400">
                            Auto-apply ≥ <span className="font-semibold text-slate-600">{profile.auto_apply_threshold}</span>
                            {" · "}
                            <span className="font-semibold text-slate-600 capitalize">{profile.auto_apply_mode || "review"}</span>
                          </span>
                          {profile.experience_level && (
                            <span className="text-[11px] text-slate-400">
                              Level: <span className="font-semibold text-slate-600 capitalize">{profile.experience_level}</span>
                            </span>
                          )}
                          {profile.last_run_at && (
                            <span className="text-[11px] text-slate-400">
                              Last run: {new Date(profile.last_run_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => handleRun(profile.id)}
                          disabled={runningId === profile.id}
                          className="btn-secondary !py-1.5 !px-3 text-[12px]"
                        >
                          {runningId === profile.id ? (
                            <>
                              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                                <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                              </svg>
                              Running…
                            </>
                          ) : (
                            <>
                              <svg className="w-3.5 h-3.5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                              Run Now
                            </>
                          )}
                        </button>
                        <button onClick={() => openEdit(profile)} className="btn-secondary !py-1.5 !px-3 text-[12px]">
                          Edit
                        </button>
                        <button
                          onClick={() => remove(profile.id)}
                          className="p-1.5 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50/70 transition-colors"
                          title="Delete"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                            <path strokeLinecap="round" strokeLinejoin="round"
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a1 1 0 00-1-1h-4a1 1 0 00-1 1H5" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
