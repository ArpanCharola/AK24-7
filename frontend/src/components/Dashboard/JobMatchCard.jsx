import { useState } from "react";
import { useNavigate } from "react-router-dom";

const MONO_COLORS = ["#7C3AED", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#3B82F6", "#EC4899"];

function domainGuess(company) {
  const slug = (company || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  return slug ? `${slug}.com` : null;
}

// Company logo: Clearbit → Google favicon → colored monogram fallback.
function CompanyLogo({ company }) {
  const [stage, setStage] = useState(0);
  const domain = domainGuess(company);
  const initial = (company || "?").trim().charAt(0).toUpperCase();
  const color = MONO_COLORS[(company || "").length % MONO_COLORS.length];

  if (!domain || stage === 2) {
    return (
      <div className="w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg flex-shrink-0"
           style={{ background: color }}>{initial}</div>
    );
  }
  const src = stage === 0
    ? `https://logo.clearbit.com/${domain}`
    : `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
  return (
    <div className="w-12 h-12 rounded-xl bg-white border border-black/5 flex items-center justify-center overflow-hidden flex-shrink-0">
      <img src={src} alt={company} className="w-full h-full object-contain p-1.5"
           onError={() => setStage((s) => s + 1)} loading="lazy" />
    </div>
  );
}

function MatchRing({ score }) {
  if (score == null) return null;
  const color = score >= 80 ? "hsl(var(--success))" : score >= 60 ? "hsl(var(--warning))" : "#94A3B8";
  return (
    <div className="relative w-12 h-12 flex-shrink-0" title={`${score}% match`}>
      <div className="absolute inset-0 rounded-full"
           style={{ background: `conic-gradient(${color} ${score * 3.6}deg, hsl(var(--muted)) 0deg)` }} />
      <div className="absolute inset-[3px] rounded-full bg-background flex items-center justify-center">
        <span className="text-[12px] font-bold" style={{ color }}>{Math.round(score)}%</span>
      </div>
    </div>
  );
}

function relTime(iso) {
  if (!iso) return null;
  const h = (Date.now() - new Date(iso).getTime()) / 36e5;
  if (h < 1) return "just now";
  if (h < 24) return `${Math.floor(h)}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function JobMatchCard({ job }) {
  const navigate = useNavigate();
  const [asked, setAsked] = useState(false);
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;

  const salary = job.salary_lpa ? `₹${Number(job.salary_lpa) % 1 === 0 ? job.salary_lpa : Number(job.salary_lpa).toFixed(1)} LPA` : job.salary_raw || null;
  const posted = relTime(job.posted_at);
  const early = job.is_early_applicant || (job.posted_at && (Date.now() - new Date(job.posted_at)) < 864e5);
  const meta = [
    job.location,
    job.work_arrangement && job.work_arrangement !== "unknown" ? job.work_arrangement : null,
    salary,
  ].filter(Boolean);

  function apply() {
    if (job.job_url) window.open(job.job_url, "_blank", "noopener");
    setAsked(true);
  }
  function tailor() {
    navigate(`/tailored-resumes?job_url=${encodeURIComponent(job.job_url || "")}`);
  }
  async function decide(decision) {
    setAsked(false);
    if (decision === "no") setHidden(true);
    try {
      const mod = await import("../../services/api");
      const apiD = mod.discoveredJobsApi || {};
      if (job.id && decision === "yes" && apiD.queue) await apiD.queue(job.id);
      if (job.id && decision === "no" && apiD.skip) await apiD.skip(job.id);
    } catch { /* non-blocking */ }
    if (decision === "yes") navigate("/tracker");
  }

  return (
    <li className="glass rounded-2xl p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3.5">
        <CompanyLogo company={job.company} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h3 className="text-[15px] font-semibold text-foreground leading-snug truncate">{job.title || "Untitled role"}</h3>
            {early && (
              <span className="flex-shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
                    style={{ background: "hsl(var(--success) / 0.12)", color: "hsl(var(--success))" }}>Early applicant</span>
            )}
          </div>
          <p className="text-[13px] text-slate-500 mt-0.5 truncate">
            <span className="font-medium text-slate-600">{job.company || "—"}</span>
            {job.source && <span className="text-slate-400 capitalize"> · {job.source}</span>}
          </p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 text-[12px] text-slate-500">
            {meta.map((m, i) => (
              <span key={i} className="inline-flex items-center capitalize">
                {i > 0 && <span className="text-slate-300 mr-2">·</span>}{m}
              </span>
            ))}
            {posted && <span className="text-slate-400">· {posted}</span>}
          </div>
          {(job.match_explanation || job.match_reason) && (
            <p className="text-[12.5px] text-slate-500 mt-2 line-clamp-2">{job.match_explanation || job.match_reason}</p>
          )}
        </div>
        <MatchRing score={job.match_score} />
      </div>

      {asked ? (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-black/5">
          <span className="text-[12.5px] font-medium text-slate-600">Did you apply?</span>
          <button onClick={() => decide("yes")} className="px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white" style={{ background: "hsl(var(--success))" }}>Yes</button>
          <button onClick={() => decide("no")} className="px-3 py-1.5 rounded-lg text-[12px] font-semibold text-slate-600 bg-muted hover:bg-muted/70">No</button>
          <button onClick={() => decide("later")} className="px-3 py-1.5 rounded-lg text-[12px] font-semibold text-slate-600 bg-muted hover:bg-muted/70">Later</button>
        </div>
      ) : (
        <div className="flex items-center gap-2 mt-3 pt-3 border-t border-black/5">
          <button onClick={apply} disabled={!job.job_url} className="btn-primary !py-1.5 !px-4 text-[12.5px] disabled:opacity-50">Apply</button>
          <button onClick={tailor} className="btn-secondary !py-1.5 !px-3 text-[12.5px]">Tailor Resume</button>
          {job.contact_linkedin && (
            <a href={job.contact_linkedin} target="_blank" rel="noopener" className="btn-secondary !py-1.5 !px-3 text-[12.5px]">HR LinkedIn</a>
          )}
        </div>
      )}
    </li>
  );
}
