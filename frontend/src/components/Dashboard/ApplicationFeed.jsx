import { useState } from "react";
import { useApplications, useRetryApplication } from "../../hooks/useApplications";

const STATUS_CONFIG = {
  pending:          { label: "Pending",       dot: "bg-amber-400" },
  running:          { label: "Running",       dot: "bg-sky-500 animate-pulse" },
  awaiting_otp:     { label: "Needs OTP",     dot: "bg-orange-500 animate-pulse" },
  awaiting_captcha: { label: "Needs CAPTCHA", dot: "bg-orange-500 animate-pulse" },
  completed:        { label: "Completed",     dot: "bg-emerald-500" },
  failed:           { label: "Failed",        dot: "bg-rose-500" },
};

// Post-submission lifecycle, derived from the user's connected Gmail.
const STAGE_CONFIG = {
  confirmed:  { label: "Confirmed ✓", short: "Confirmed",  cls: "bg-emerald-100/80 text-emerald-700" },
  assessment: { label: "Assessment",  short: "Assessment", cls: "bg-violet-100/80 text-violet-700" },
  interview:  { label: "Interview",   short: "Interview",  cls: "bg-sky-100/80 text-sky-700" },
  offer:      { label: "Offer 🎉",    short: "Offer",      cls: "bg-amber-100/90 text-amber-700" },
  rejected:   { label: "Rejected",    short: "Rejected",   cls: "bg-slate-200/70 text-slate-500" },
};
// Funnel order for the pipeline summary strip.
const PIPELINE_ORDER = ["confirmed", "assessment", "interview", "offer", "rejected"];

function PipelineSummary({ applications }) {
  const counts = applications.reduce((acc, a) => {
    if (a.stage) acc[a.stage] = (acc[a.stage] || 0) + 1;
    return acc;
  }, {});
  const tracked = PIPELINE_ORDER.filter((k) => counts[k]);
  if (tracked.length === 0) return null; // nothing detected from Gmail yet
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 py-2.5 border-b border-white/40">
      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mr-1">Pipeline</span>
      {tracked.map((k) => (
        <span key={k} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10.5px] font-semibold ${STAGE_CONFIG[k].cls}`}>
          {STAGE_CONFIG[k].short} <span className="opacity-70">{counts[k]}</span>
        </span>
      ))}
    </div>
  );
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function ApplicationFeed({ onSelect, selectedId }) {
  const { data: applications, isLoading } = useApplications();
  const { mutate: retry } = useRetryApplication();
  const [retryingId, setRetryingId] = useState(null);

  function handleRetry(id) {
    setRetryingId(id);
    retry(id, { onSettled: () => setRetryingId(null) });
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-white/40 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (!applications?.length) {
    return (
      <div className="flex flex-col items-center justify-center h-56 text-center px-6">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
             style={{ background: "hsl(var(--muted))" }}>
          <svg className="w-6 h-6 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </div>
        <p className="text-sm text-slate-700 font-semibold">No applications yet</p>
        <p className="text-xs text-slate-400 mt-1 max-w-[180px]">Paste a job URL above to get started</p>
      </div>
    );
  }

  return (
    <>
    <PipelineSummary applications={applications} />
    <ul className="px-2 py-2 space-y-1">
      {applications.map((app) => {
        const cfg = STATUS_CONFIG[app.status] || { label: app.status, dot: "bg-slate-400" };
        const isSelected = selectedId === app.id;
        return (
          <li key={app.id}>
            <button
              type="button"
              onClick={() => onSelect(app.id)}
              className={`group relative w-full text-left px-3 py-3 rounded-xl transition-all duration-200 ${
                isSelected
                  ? "bg-white/85 shadow-glass"
                  : "hover:bg-white/55"
              }`}
            >
              {isSelected && (
                <span aria-hidden
                  className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full"
                  style={{ background: "hsl(var(--primary))" }}
                />
              )}
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-[13.5px] font-semibold text-slate-900 truncate leading-tight">
                    {app.job_title || "Untitled Job"}
                  </p>
                  <p className="text-[11.5px] text-slate-500 truncate mt-0.5">
                    {app.company || app.job_url}
                  </p>
                </div>
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className="inline-flex items-center gap-1.5 text-[10.5px] font-semibold text-slate-600">
                  <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                  {cfg.label}
                  {app.queued_by === "auto" && (
                    <span
                      title="Queued automatically by auto-apply"
                      className="ml-1 inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-accent-100/80 text-accent-700 text-[9.5px] font-bold tracking-wide"
                    >
                      AUTO
                    </span>
                  )}
                  {app.stage && STAGE_CONFIG[app.stage] && (
                    <span
                      title="Detected from your connected Gmail"
                      className={`ml-1 inline-flex items-center px-1.5 py-0.5 rounded-md text-[9.5px] font-bold tracking-wide ${STAGE_CONFIG[app.stage].cls}`}
                    >
                      {STAGE_CONFIG[app.stage].label}
                    </span>
                  )}
                </span>
                {app.created_at && (
                  <span className="text-[10.5px] text-slate-400 font-medium">{timeAgo(app.created_at)}</span>
                )}
              </div>
            </button>

            {app.status === "failed" && (
              <div className="px-3 pb-2.5 pt-0.5">
                {app.error_message && (
                  <p className="text-[10.5px] text-rose-500/90 mb-1.5 line-clamp-2" title={app.error_message}>
                    {app.error_message}
                  </p>
                )}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); handleRetry(app.id); }}
                  disabled={retryingId === app.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-rose-50 text-rose-600 hover:bg-rose-100 disabled:opacity-50 transition-colors"
                >
                  <svg className={`w-3 h-3 ${retryingId === app.id ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  {retryingId === app.id ? "Retrying…" : "Retry"}
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
    </>
  );
}
