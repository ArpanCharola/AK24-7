import { useNavigate } from "react-router-dom";

// Normalize missing_skills which may arrive as a JSON-encoded list, a
// comma-separated string, or an actual array (contract #6 stores it as Text).
function toList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.filter(Boolean);
  if (typeof value === "string") {
    const s = value.trim();
    if (!s) return [];
    if (s.startsWith("[")) {
      try {
        const parsed = JSON.parse(s);
        if (Array.isArray(parsed)) return parsed.filter(Boolean);
      } catch {
        /* fall through to comma split */
      }
    }
    return s.split(",").map((x) => x.trim()).filter(Boolean);
  }
  return [];
}

function formatSalary(job) {
  if (job.salary_lpa != null && job.salary_lpa !== "") {
    const n = Number(job.salary_lpa);
    if (!Number.isNaN(n) && n > 0) return `₹${n % 1 === 0 ? n : n.toFixed(1)} LPA`;
  }
  return job.salary_raw || null;
}

function scoreTones(score) {
  if (score >= 80) return { ring: "#10b981", text: "text-emerald-600", chip: "bg-emerald-100/80 text-emerald-700 border-emerald-200/60" };
  if (score >= 60) return { ring: "#f59e0b", text: "text-amber-600", chip: "bg-amber-100/80 text-amber-700 border-amber-200/60" };
  return { ring: "#f43f5e", text: "text-rose-600", chip: "bg-rose-100/80 text-rose-700 border-rose-200/60" };
}

function ScoreRing({ score }) {
  if (score == null) {
    return (
      <div className="flex flex-col items-center justify-center w-14 h-14 rounded-full border border-dashed border-slate-300 text-slate-400">
        <span className="text-[10px] font-semibold">N/A</span>
      </div>
    );
  }
  const { ring, text } = scoreTones(score);
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="relative w-14 h-14 rounded-full flex items-center justify-center flex-shrink-0"
      style={{ background: `conic-gradient(${ring} ${pct * 3.6}deg, hsl(var(--muted)) 0deg)` }}
    >
      <div className="absolute inset-[3px] rounded-full flex flex-col items-center justify-center" style={{ background: "hsl(var(--card))" }}>
        <span className={`text-[15px] font-bold leading-none ${text}`}>{Math.round(score)}</span>
        <span className="text-[8px] font-semibold uppercase tracking-wider text-slate-400">match</span>
      </div>
    </div>
  );
}

export default function JobMatchCard({ job }) {
  const navigate = useNavigate();
  const missing = toList(job.missing_skills);
  const salary = formatSalary(job);
  const whyFit = job.match_explanation || job.match_reason;
  const { chip } = scoreTones(job.match_score ?? 0);

  function tailorForJob() {
    const params = new URLSearchParams();
    if (job.job_url) params.set("job_url", job.job_url);
    navigate(`/tailored-resumes${params.toString() ? `?${params}` : ""}`);
  }

  function askOrion() {
    const params = new URLSearchParams();
    if (job.id != null) params.set("job_id", String(job.id));
    navigate(`/copilot${params.toString() ? `?${params}` : ""}`);
  }

  return (
    <li className="group glass-subtle rounded-2xl hover:bg-white/65 transition-all duration-200">
      <div className="p-4 flex items-start gap-4">
        <ScoreRing score={job.match_score} />

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-[15px] font-semibold text-slate-900 leading-tight truncate">
                {job.title || "Untitled role"}
              </h3>
              <p className="text-[12.5px] text-slate-500 mt-0.5">
                <span className="font-semibold text-slate-700">{job.company || "—"}</span>
                {job.location && <> · {job.location}</>}
              </p>
            </div>
            {job.source && (
              <span className="pill border bg-slate-100/80 text-slate-600 border-slate-200/60 capitalize flex-shrink-0">
                {job.source}
              </span>
            )}
          </div>

          {/* Meta chips: salary, notice period, work arrangement, posted */}
          <div className="flex flex-wrap items-center gap-1.5 mt-2.5">
            {salary && (
              <span className="pill border bg-emerald-100/80 text-emerald-700 border-emerald-200/60">
                {salary}
              </span>
            )}
            {job.notice_period && (
              <span className="pill border bg-sky-100/80 text-sky-700 border-sky-200/60">
                Notice: {job.notice_period}
              </span>
            )}
            {job.work_arrangement && job.work_arrangement !== "unknown" && (
              <span className="pill border bg-violet-100/80 text-violet-700 border-violet-200/60 capitalize">
                {job.work_arrangement}
              </span>
            )}
            {job.posted_at && (
              <span className="text-[11px] text-slate-400 font-medium">
                {new Date(job.posted_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
              </span>
            )}
          </div>

          {/* Why-fit */}
          {whyFit && (
            <div className="mt-3 flex items-start gap-2">
              <svg className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              <p className="text-[12px] text-slate-600 leading-relaxed line-clamp-3">{whyFit}</p>
            </div>
          )}

          {/* Missing skills */}
          {missing.length > 0 && (
            <div className="mt-2.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mr-1.5">
                Skill gaps
              </span>
              <span className="inline-flex flex-wrap gap-1.5 align-middle">
                {missing.slice(0, 6).map((skill, i) => (
                  <span key={i} className="pill border bg-rose-50/80 text-rose-600 border-rose-200/60">
                    {skill}
                  </span>
                ))}
                {missing.length > 6 && (
                  <span className="text-[11px] text-slate-400 font-medium self-center">+{missing.length - 6}</span>
                )}
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2 mt-3.5">
            {job.job_url && (
              <a
                href={job.job_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary !py-1.5 !px-3 text-[12px]"
              >
                <svg className="w-3.5 h-3.5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                View job
              </a>
            )}
            <button type="button" onClick={tailorForJob} className="btn-primary !py-1.5 !px-3 text-[12px]">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Tailor resume
            </button>
            <button type="button" onClick={askOrion} className={`pill border ${chip} hover:opacity-80 transition-opacity`}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.5C3.5 15.3 3 13.7 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Ask Orion
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}
