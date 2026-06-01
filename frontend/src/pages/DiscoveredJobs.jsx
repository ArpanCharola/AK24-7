import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useDiscoveredJobs,
  useQueueJob,
  useSkipJob,
  useDeleteJob,
  useBulkDeleteJobs,
  useBulkQueueJobs,
  useFindContact,
} from "../hooks/useDiscoveredJobs";
import { discoveredJobsApi } from "../services/api";

const TABS = [
  { label: "All",         value: undefined },
  { label: "New",         value: "discovered" },
  { label: "Needs review", value: "auto_queued" },
  { label: "Queued",      value: "queued" },
  { label: "Skipped",     value: "skipped" },
];

const DATE_OPTIONS = [
  { label: "Any time",     value: "" },
  { label: "Last 24 hours", value: "1" },
  { label: "Last 3 days",  value: "3" },
  { label: "Last 7 days",  value: "7" },
  { label: "Last 14 days", value: "14" },
  { label: "Last 30 days", value: "30" },
];

function SelectFilter({ value, onChange, options }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, []);

  const selected = options.find((o) => o.value === value) ?? options[0];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="input-glass !w-auto !py-1.5 !pl-3 !pr-2.5 text-[12.5px] flex items-center gap-1.5 cursor-pointer"
      >
        <span className="font-medium">{selected.label}</span>
        <svg
          className={`w-3.5 h-3.5 text-slate-400 flex-shrink-0 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 z-50 glass rounded-2xl overflow-hidden min-w-[148px]"
             style={{ boxShadow: "0 8px 32px -8px rgba(0,0,0,0.2), 0 2px 8px -2px rgba(0,0,0,0.1)" }}>
          <ul className="py-1.5">
            {options.map((opt) => {
              const active = opt.value === value;
              return (
                <li key={opt.value}>
                  <button
                    type="button"
                    onClick={() => { onChange(opt.value); setOpen(false); }}
                    className={`w-full text-left px-3.5 py-2 text-[12.5px] font-medium transition-all duration-100 ${
                      active
                        ? "text-accent-600 bg-accent-50/40"
                        : "text-slate-700 hover:bg-white/55 hover:text-slate-900"
                    }`}
                  >
                    {opt.label}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

const SOURCE_COLORS = {
  greenhouse:      "bg-emerald-100/80 text-emerald-700 border-emerald-200/60",
  lever:           "bg-sky-100/80 text-sky-700 border-sky-200/60",
  ashby:           "bg-violet-100/80 text-violet-700 border-violet-200/60",
  workday:         "bg-orange-100/80 text-orange-700 border-orange-200/60",
  icims:           "bg-amber-100/80 text-amber-700 border-amber-200/60",
  smartrecruiters: "bg-teal-100/80 text-teal-700 border-teal-200/60",
  bamboohr:        "bg-lime-100/80 text-lime-700 border-lime-200/60",
  adp:             "bg-red-100/80 text-red-700 border-red-200/60",
  oracle:          "bg-rose-100/80 text-rose-700 border-rose-200/60",
  adzuna:          "bg-pink-100/80 text-pink-700 border-pink-200/60",
};

function ScoreBadge({ score }) {
  if (score === null || score === undefined)
    return <span className="text-[11px] text-slate-400 italic">Unscored</span>;
  const [bg, text, border] =
    score >= 80 ? ["bg-emerald-100/80", "text-emerald-700", "border-emerald-200/60"] :
    score >= 60 ? ["bg-amber-100/80",   "text-amber-700",   "border-amber-200/60"] :
                  ["bg-rose-100/80",    "text-rose-700",    "border-rose-200/60"];
  return (
    <span className={`pill border ${bg} ${text} ${border}`}>
      {score}% match
    </span>
  );
}

function ScoreBar({ score }) {
  if (score === null || score === undefined) return null;
  const gradient =
    score >= 80 ? "from-emerald-400 to-emerald-500" :
    score >= 60 ? "from-amber-400 to-amber-500" :
                  "from-rose-400 to-rose-500";
  return (
    <div className="flex items-center gap-2 mt-2">
      <div className="flex-1 h-1 bg-slate-200/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${gradient} transition-all`}
             style={{ width: `${score}%` }} />
      </div>
    </div>
  );
}

export default function DiscoveredJobs() {
  const [activeTab, setActiveTab] = useState(undefined);
  const [postedDays, setPostedDays] = useState(null);
  const { data: jobs = [], isLoading } = useDiscoveredJobs(activeTab, postedDays);
  const { mutate: queue } = useQueueJob();
  const { mutate: skip } = useSkipJob();
  const { mutate: remove } = useDeleteJob();
  const { mutate: bulkDelete, isPending: bulkDeleting } = useBulkDeleteJobs();
  const { mutate: bulkQueue, isPending: bulkQueuing } = useBulkQueueJobs();
  const { mutateAsync: findContact } = useFindContact();
  const navigate = useNavigate();

  const [loadingId, setLoadingId] = useState(null);
  const [contactLoadingId, setContactLoadingId] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [exporting, setExporting] = useState(false);
  const [bulkMsg, setBulkMsg] = useState("");

  async function handleFindContact(id) {
    setContactLoadingId(id);
    try {
      await findContact({ id, useApify: true });
    } catch (e) {
      console.error("Find contact failed", e);
    } finally {
      setContactLoadingId(null);
    }
  }

  function handleReachOut(job) {
    // Navigate to email-auto with the job context as query params; EmailAuto
    // reads these and pre-fills the compose modal via /email/compose.
    const params = new URLSearchParams({
      to: job.contact_email || "",
      job_id: String(job.id),
      company: job.company || "",
      role: job.title || "",
    });
    navigate(`/email-auto?${params.toString()}`);
  }

  async function handleExport() {
    setExporting(true);
    try {
      const res = await discoveredJobsApi.export(activeTab, postedDays);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `discovered_jobs_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  const allIds = jobs.map((j) => j.id);
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const someSelected = selected.size > 0;

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(allIds));
  }

  function toggleOne(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function handleQueue(id) {
    setLoadingId(id);
    queue(id, { onSettled: () => setLoadingId(null) });
  }

  function handleBulkDelete() {
    bulkDelete([...selected], { onSuccess: () => setSelected(new Set()) });
  }

  function handleBulkQueue() {
    const ids = [...selected];
    if (ids.length === 0) return;
    if (!window.confirm(`Apply to ${ids.length} selected job(s)? Each will be tailored and submitted automatically.`)) return;
    bulkQueue(ids, {
      onSuccess: (data) => {
        setSelected(new Set());
        const q = data?.queued?.length ?? 0;
        const s = data?.skipped?.length ?? 0;
        setBulkMsg(`Queued ${q} application(s)${s ? ` · skipped ${s} (already applied or not queueable)` : ""}.`);
        setTimeout(() => setBulkMsg(""), 6000);
      },
      onError: () => {
        setBulkMsg("Bulk apply failed — please try again.");
        setTimeout(() => setBulkMsg(""), 6000);
      },
    });
  }

  function handleTabChange(value) {
    setActiveTab(value);
    setSelected(new Set());
  }

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      {/* Header */}
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Discovered Jobs</h1>
            <p className="text-[13px] text-slate-500 mt-0.5">Matched from your search profiles, scored by AI</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleExport} disabled={exporting || jobs.length === 0} className="btn-secondary text-[12.5px]">
              <svg className="w-4 h-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              {exporting ? "Exporting…" : "Export"}
            </button>
            <a href="/job-preferences" className="btn-secondary text-[12.5px]">
              <svg className="w-4 h-4 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Profiles
            </a>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-6 space-y-4">
          {/* Tabs + filter row */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            {/* Tabs */}
            <div className="inline-flex items-center gap-1 glass-subtle rounded-2xl p-1">
              {TABS.map((tab) => {
                const active = activeTab === tab.value;
                return (
                  <button
                    key={tab.label}
                    onClick={() => handleTabChange(tab.value)}
                    className={`relative px-4 py-1.5 rounded-xl text-[12.5px] font-semibold transition-all ${
                      active ? "text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {active && (
                      <span aria-hidden className="absolute inset-0 rounded-xl"
                            style={{
                              background: "hsl(var(--primary))",
                              boxShadow: "0 4px 14px -4px rgba(107,61,245,0.5)",
                            }} />
                    )}
                    <span className="relative z-10">{tab.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Posted within */}
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span className="text-[12px] text-slate-500 font-medium">Posted within</span>
              <SelectFilter
                value={postedDays != null ? String(postedDays) : ""}
                onChange={(v) => setPostedDays(v ? Number(v) : null)}
                options={DATE_OPTIONS}
              />
            </div>
          </div>

          {/* Bulk action bar */}
          {jobs.length > 0 && (
            <div className="flex items-center gap-3 px-1">
              <label className="flex items-center gap-2 text-[13px] text-slate-600 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="accent-accent-600 w-4 h-4 rounded"
                />
                {allSelected ? "Deselect all" : "Select all"}
              </label>
              {someSelected && (
                <>
                  <span className="pill bg-accent-100/80 text-accent-700">
                    {selected.size} selected
                  </span>
                  <button
                    onClick={handleBulkQueue}
                    disabled={bulkQueuing}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-50 transition-all shadow-sm"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    {bulkQueuing ? "Applying…" : `Apply ${selected.size}`}
                  </button>
                  <button
                    onClick={handleBulkDelete}
                    disabled={bulkDeleting}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold bg-rose-600 text-white rounded-xl hover:bg-rose-700 disabled:opacity-50 transition-all shadow-sm"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a1 1 0 00-1-1h-4a1 1 0 00-1 1H5" />
                    </svg>
                    {bulkDeleting ? "Deleting…" : `Delete ${selected.size}`}
                  </button>
                </>
              )}
            </div>
          )}

          {bulkMsg && (
            <div className="mb-4 px-4 py-2.5 rounded-xl text-[13px] glass-subtle text-slate-700 border border-emerald-200/60">
              {bulkMsg}
            </div>
          )}

          {/* List */}
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-32 glass-subtle rounded-2xl animate-pulse" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="glass-subtle rounded-2xl p-14 text-center">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
                   style={{ background: "hsl(var(--muted))" }}>
                <svg className="w-7 h-7 text-accent-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z" />
                </svg>
              </div>
              <p className="text-slate-800 font-semibold text-sm">No jobs found</p>
              <p className="text-slate-400 text-[12.5px] mt-1">
                {activeTab ? "Try a different filter." : "Go to Search Profiles and run a profile to discover jobs."}
              </p>
            </div>
          ) : (
            <ul className="space-y-3">
              {jobs.map((job) => (
                <li
                  key={job.id}
                  className={`group rounded-2xl transition-all duration-200 ${
                    selected.has(job.id)
                      ? "glass-strong ring-2 ring-accent-300/60"
                      : "glass-subtle hover:bg-white/65"
                  }`}
                >
                  <div className="p-4 flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selected.has(job.id)}
                      onChange={() => toggleOne(job.id)}
                      className="mt-1 accent-accent-600 w-4 h-4 flex-shrink-0 cursor-pointer"
                    />

                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <h3 className="text-[14px] font-semibold text-slate-900 leading-tight">
                              {job.title || "Untitled"}
                            </h3>
                            <span className={`pill border capitalize ${SOURCE_COLORS[job.source] || "bg-slate-100/80 text-slate-600 border-slate-200/60"}`}>
                              {job.source}
                            </span>
                            <ScoreBadge score={job.match_score} />
                            {job.work_arrangement && job.work_arrangement !== "unknown" && (
                              <span className="pill bg-slate-100/80 text-slate-600 border border-slate-200/60 capitalize">
                                {job.work_arrangement}
                              </span>
                            )}
                          </div>

                          <p className="text-[12.5px] text-slate-500">
                            <span className="font-semibold text-slate-700">{job.company || "—"}</span>
                            {job.location && <> · {job.location}</>}
                            {job.posted_at && (
                              <span className="text-slate-400 ml-2">
                                · {new Date(job.posted_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                              </span>
                            )}
                          </p>

                          <ScoreBar score={job.match_score} />

                          {job.match_reason && (
                            <p className="text-[11.5px] text-slate-500 mt-2 line-clamp-2 leading-relaxed">
                              {job.match_reason}
                            </p>
                          )}

                          <a
                            href={job.job_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[11.5px] text-accent-600 hover:text-accent-700 hover:underline mt-2 inline-flex items-center gap-1 max-w-xs truncate"
                          >
                            <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 11-5.656-5.656l1.5-1.5" />
                              <path strokeLinecap="round" strokeLinejoin="round" d="M10.172 13.828a4 4 0 010-5.656l3-3a4 4 0 015.656 5.656l-1.5 1.5" />
                            </svg>
                            <span className="truncate">{job.job_url}</span>
                          </a>

                          {(job.contact_email || job.contact_linkedin || job.contact_name) && (
                            <div className="mt-2 flex items-center flex-wrap gap-x-3 gap-y-1 text-[11.5px]">
                              {job.contact_name && (
                                <span className="text-slate-600 font-medium">{job.contact_name}</span>
                              )}
                              {job.contact_email && (
                                <a
                                  href={`mailto:${job.contact_email}`}
                                  className="text-accent-600 hover:text-accent-700 hover:underline inline-flex items-center gap-1"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                  </svg>
                                  {job.contact_email}
                                </a>
                              )}
                              {job.contact_linkedin && (
                                <a
                                  href={job.contact_linkedin}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-accent-600 hover:text-accent-700 hover:underline inline-flex items-center gap-1"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M19 0h-14C2.24 0 0 2.24 0 5v14c0 2.76 2.24 5 5 5h14c2.76 0 5-2.24 5-5V5c0-2.76-2.24-5-5-5zM8 19H5V8h3v11zM6.5 6.73a1.75 1.75 0 110-3.5 1.75 1.75 0 010 3.5zM20 19h-3v-5.6c0-1.34-.02-3.07-1.87-3.07-1.87 0-2.16 1.46-2.16 2.97V19h-3V8h2.88v1.51h.04c.4-.76 1.39-1.56 2.86-1.56 3.06 0 3.63 2.02 3.63 4.64V19z" />
                                  </svg>
                                  LinkedIn
                                </a>
                              )}
                              {job.contact_source && (
                                <span
                                  className="text-[10px] text-slate-400 uppercase tracking-wider"
                                  title={`Source: ${job.contact_source}`}
                                >
                                  · {job.contact_source.replace("_", " ")}
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                          <div className="flex items-center gap-1.5">
                          {job.status === "discovered" && (
                            <>
                              <button
                                onClick={() => handleQueue(job.id)}
                                disabled={loadingId === job.id}
                                className="btn-primary !py-1.5 !px-3 text-[12px]"
                              >
                                {loadingId === job.id ? "Queuing…" : "Apply"}
                              </button>
                              <button
                                onClick={() => skip(job.id)}
                                className="btn-secondary !py-1.5 !px-3 text-[12px]"
                              >
                                Skip
                              </button>
                            </>
                          )}
                          {job.status === "auto_queued" && (
                            <>
                              <span className="pill bg-amber-100/80 text-amber-700 border border-amber-200/60">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                                Auto-queued
                              </span>
                              <button
                                onClick={() => handleQueue(job.id)}
                                disabled={loadingId === job.id}
                                className="btn-primary !py-1.5 !px-3 text-[12px]"
                                title="Approve & Apply"
                              >
                                {loadingId === job.id ? "Queuing…" : "Approve"}
                              </button>
                              <button
                                onClick={() => skip(job.id)}
                                className="btn-secondary !py-1.5 !px-3 text-[12px]"
                              >
                                Skip
                              </button>
                            </>
                          )}
                          {job.status === "queued" && (
                            <span className="pill bg-sky-100/80 text-sky-700 border border-sky-200/60">
                              Queued
                            </span>
                          )}
                          {job.status === "skipped" && (
                            <span className="pill bg-slate-100/80 text-slate-500 border border-slate-200/60">
                              Skipped
                            </span>
                          )}
                          <button
                            onClick={() => remove(job.id)}
                            title="Delete"
                            className="p-1.5 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50/70 transition-colors"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                              <path strokeLinecap="round" strokeLinejoin="round"
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a1 1 0 00-1-1h-4a1 1 0 00-1 1H5" />
                            </svg>
                          </button>
                          </div>

                          {/* Contact actions — always shown */}
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => handleFindContact(job.id)}
                              disabled={contactLoadingId === job.id}
                              className="btn-secondary !py-1 !px-2.5 text-[11px] inline-flex items-center gap-1"
                              title={job.contact_email
                                ? `Re-find (current: ${job.contact_source || "unknown"})`
                                : "Search the company site for a recruiter email + LinkedIn"}
                            >
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                              </svg>
                              {contactLoadingId === job.id
                                ? "Searching…"
                                : (job.contact_email ? "Re-find" : "Find contact")}
                            </button>
                            {job.contact_email && (
                              <button
                                onClick={() => handleReachOut(job)}
                                className="btn-primary !py-1 !px-2.5 text-[11px] inline-flex items-center gap-1"
                                title={`Compose an email to ${job.contact_email}`}
                              >
                                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                                Reach out
                              </button>
                            )}
                          </div>
                        </div>
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
