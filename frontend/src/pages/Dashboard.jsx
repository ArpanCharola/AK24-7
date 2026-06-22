import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Briefcase, Send, Target } from "lucide-react";
import { authApi } from "../services/api";
import { useDashboardStats } from "../hooks/useDashboard";
import { useMatches } from "../hooks/useMatches";
import JobMatchCard from "../components/Jobs/JobMatchCard";

function Tile({ icon: Icon, label, value, sub, onClick }) {
  return (
    <button onClick={onClick} className="glass rounded-2xl p-5 text-left hover-lift group">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon size={15} strokeWidth={1.75} />
        <span className="text-[11px] font-semibold uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-[32px] leading-none font-display font-bold mt-3 text-foreground tnum">{value}</p>
      <p className="text-[12px] text-muted-foreground/80 mt-2 group-hover:text-muted-foreground transition-colors">{sub}</p>
    </button>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
  const { data: stats } = useDashboardStats();
  const { data: matches = [] } = useMatches({ sort: "recent" });

  const roles = stats?.target_roles || [];
  const recent = (Array.isArray(matches) ? matches : []).slice(0, 6);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (me?.full_name || me?.username || "").trim().split(" ")[0];

  return (
    <div className="p-6 w-full max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {greeting}{firstName ? `, ${firstName}` : ""} 👋
        </h1>
        <p className="text-[13px] text-muted-foreground mt-0.5">Here's your job search at a glance.</p>
      </div>

      {/* 3 real-number tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <Tile icon={Briefcase} label="Jobs Found" value={stats?.jobs_found ?? "—"}
              sub="View all jobs →" onClick={() => navigate("/jobs")} />
        <Tile icon={Send} label="Applied" value={stats?.jobs_applied ?? "—"}
              sub="Open tracker →" onClick={() => navigate("/tracker")} />
        <Tile icon={Target} label="Target Roles" value={roles.length || "—"}
              sub={roles.length ? roles.join(" · ") : "Set in profile →"} onClick={() => navigate("/profile")} />
      </div>

      {/* Recent matches */}
      <div className="flex items-center justify-between mt-8 mb-3">
        <h2 className="text-[15px] font-semibold text-foreground">Recent matches</h2>
        <button onClick={() => navigate("/jobs")} className="text-[12.5px] font-semibold text-brand hover:underline">
          View all in Jobs →
        </button>
      </div>

      {recent.length === 0 ? (
        <div className="glass-subtle rounded-2xl p-10 text-center">
          <p className="text-foreground font-semibold text-sm">No matches yet</p>
          <p className="text-muted-foreground text-[12.5px] mt-1 max-w-sm mx-auto">
            Complete your profile, then open Jobs and run a search to discover India roles.
          </p>
          <div className="flex items-center justify-center gap-2 mt-4">
            <button onClick={() => navigate("/profile")} className="btn-secondary text-[12.5px]">Complete profile</button>
            <button onClick={() => navigate("/jobs")} className="btn-primary text-[12.5px]">Go to Jobs</button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {recent.map((job) => (
            <JobMatchCard key={job.id ?? job.job_url} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
