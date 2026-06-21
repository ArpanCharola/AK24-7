import { useNavigate } from "react-router-dom";
import { MapPin, Briefcase, ExternalLink, FileText, Clock, Zap } from "lucide-react";
import { timeAgo, salaryLabel } from "../../lib/format";

function MatchBadge({ score }) {
  if (score == null) return null;
  const cls =
    score >= 80 ? "pill-success" :
    score >= 60 ? "pill-warning" :
    "pill";
  return <span className={`pill ${cls} tnum`}>{score}% match</span>;
}

function LogoAvatar({ name }) {
  const initials = (name || "?").slice(0, 2).toUpperCase();
  return (
    <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center text-brand text-[13px] font-bold shrink-0">
      {initials}
    </div>
  );
}

// Elevated, Jobright-style match card. Match score renders only when real
// (match_score != null) — never a placeholder.
export default function JobMatchCard({ job }) {
  const navigate = useNavigate();
  const salary = salaryLabel(job);

  function tailorAndApply() {
    // Stash the job so the "Did you apply?" prompt can offer to add it to the
    // tracker when the user returns from applying.
    localStorage.setItem(
      "pendingApply",
      JSON.stringify({ company: job.company, role: job.title, job_link: job.job_url })
    );
    // The tailor page auto-extracts the JD from ?job_url=.
    const q = job.job_url ? `?job_url=${encodeURIComponent(job.job_url)}` : "";
    navigate(`/tailor-resume${q}`);
  }

  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-3 hover-lift">
      <div className="flex items-start gap-3">
        <LogoAvatar name={job.company} />
        <div className="flex-1 min-w-0">
          <p className="text-[13.5px] font-semibold text-foreground truncate">{job.company || "Unknown company"}</p>
          <p className="text-[12.5px] text-muted-foreground truncate">{job.title || "Role"}</p>
        </div>
        <MatchBadge score={job.match_score} />
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-muted-foreground">
        {job.location && <span className="inline-flex items-center gap-1"><MapPin size={12} />{job.location}</span>}
        {job.work_arrangement && <span className="inline-flex items-center gap-1"><Briefcase size={12} />{job.work_arrangement}</span>}
        {salary && <span className="tnum">{salary}</span>}
        {job.posted_at && <span className="inline-flex items-center gap-1"><Clock size={12} />{timeAgo(job.posted_at)}</span>}
        {job.is_early_applicant && (
          <span className="pill pill-brand"><Zap size={11} /> Early applicant</span>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1 border-t border-border">
        <button onClick={tailorAndApply} className="btn-gradient !py-1.5 !px-3 text-[12px] flex-1">
          <FileText size={13} /> Tailor &amp; Apply
        </button>
        {job.job_url && (
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary !py-1.5 !px-3 text-[12px]"
            title="Open job description"
          >
            <ExternalLink size={13} /> JD
          </a>
        )}
      </div>
    </div>
  );
}
