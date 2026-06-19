import { useNavigate } from "react-router-dom";
import { useDashboardStats } from "../hooks/useDashboard";
import { useMatches } from "../hooks/useMatches";
import JobMatchCard from "../components/Dashboard/JobMatchCard";

function Tile({ label, value, sub, onClick, accent }) {
  return (
    <button
      onClick={onClick}
      className="glass rounded-2xl p-5 text-left hover:shadow-md transition-all active:scale-[0.99] group"
    >
      <p className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="text-[34px] leading-none font-display font-bold mt-3" style={{ color: accent }}>{value}</p>
      <p className="text-[12px] text-slate-400 mt-2 group-hover:text-slate-600 transition-colors">{sub}</p>
    </button>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: stats } = useDashboardStats();
  const { data: matches = [] } = useMatches({ sort: "recent" });

  const roles = stats?.target_roles || [];
  const recent = (Array.isArray(matches) ? matches : []).slice(0, 5);

  return (
    <div className="h-full overflow-y-auto animate-fade-in">
      <div className="max-w-5xl mx-auto p-1 sm:p-2">
        <h1 className="text-[24px] font-display font-bold text-foreground tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Your job search at a glance.</p>

        {/* 4 real-number tiles */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          <Tile
            label="Jobs Found"
            value={stats?.jobs_found ?? "—"}
            sub="View all jobs →"
            accent="hsl(var(--brand))"
            onClick={() => navigate("/discovered-jobs")}
          />
          <Tile
            label="Jobs Applied"
            value={stats?.jobs_applied ?? "—"}
            sub="Open tracker →"
            accent="hsl(var(--success))"
            onClick={() => navigate("/tracker")}
          />
          <Tile
            label="Target Roles"
            value={roles.length || "—"}
            sub={roles.length ? roles.join(" · ") : "Set in profile →"}
            accent="hsl(var(--brand-2))"
            onClick={() => navigate("/profile")}
          />
          <Tile
            label="Tailored Resumes"
            value={stats?.tailored_resumes ?? "—"}
            sub="Resume history →"
            accent="hsl(var(--warning))"
            onClick={() => navigate("/tailored-resumes")}
          />
        </div>

        {/* Compact recent matches strip */}
        <div className="flex items-center justify-between mt-7 mb-3">
          <h2 className="text-[15px] font-semibold text-foreground">Recent matches</h2>
          <button onClick={() => navigate("/discovered-jobs")} className="text-[12.5px] font-semibold text-brand hover:underline">
            View all in Jobs →
          </button>
        </div>

        {recent.length === 0 ? (
          <div className="glass-subtle rounded-2xl p-10 text-center">
            <p className="text-foreground font-semibold text-sm">No matches yet</p>
            <p className="text-slate-400 text-[12.5px] mt-1 max-w-sm mx-auto">
              Complete your profile, then open Jobs and import a profile to discover roles.
            </p>
            <div className="flex items-center justify-center gap-2 mt-4">
              <button onClick={() => navigate("/profile")} className="btn-secondary text-[12.5px]">Complete profile</button>
              <button onClick={() => navigate("/discovered-jobs")} className="btn-primary text-[12.5px]">Go to Jobs</button>
            </div>
          </div>
        ) : (
          <ul className="space-y-3">
            {recent.map((job) => (
              <JobMatchCard key={job.id ?? job.job_url} job={job} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
