import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BriefcaseBusiness, Send, Sparkles, Target } from "lucide-react";
import { useEffect } from "react";
import { authApi } from "../services/api";
import { useDashboardStats } from "../hooks/useDashboard";
import { useMatches } from "../hooks/useMatches";
import JobMatchCard from "../components/Jobs/JobMatchCard";

function Metric({ icon: Icon, label, value, detail, onClick }) {
  return (
    <button onClick={onClick} className="glass group metric-card rounded-3xl text-left hover-lift">
      <div className="metric-label">
        <span>{label}</span>
        <Icon size={19} />
      </div>
      <strong>{value}</strong>
      <span className="metric-detail">{detail}</span>
    </button>
  );
}

function QuickLink({ title, copy, action, onClick }) {
  return (
    <button onClick={onClick} className="glass-subtle rounded-3xl p-5 text-left transition-all hover:-translate-y-0.5 hover:border-brand/30">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-[13px] leading-6 text-muted-foreground">{copy}</p>
        </div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-brand">
          {action}
          <ArrowRight size={12} />
        </span>
      </div>
    </button>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    staleTime: 300000,
  });
  const { data: stats } = useDashboardStats();
  const { data: matches = [] } = useMatches({ sort: "recent" });

  useEffect(() => {
    if (me?.is_admin) navigate("/admin", { replace: true });
  }, [me?.is_admin, navigate]);

  if (me?.is_admin) return null;

  const roles = stats?.target_roles || [];
  const recent = (Array.isArray(matches) ? matches : []).slice(0, 6);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (me?.full_name || me?.username || "").trim().split(" ")[0];

  return (
    <div className="page-wrap dashboard-page space-y-8">
      <section className="dashboard-hero rounded-[32px] border border-white/10 bg-[linear-gradient(135deg,#0f2ea8_0%,#253dce_50%,#6d28d9_140%)] px-7 py-8 text-white shadow-[0_30px_90px_-46px_rgba(37,61,206,0.52)] md:px-10 md:py-10">
        <div className="hero-copy max-w-3xl">
          <span className="inline-flex rounded-full border border-white/14 bg-white/8 px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-white/82">Career cockpit · curated daily</span>
          <h1>
            {greeting}
            {firstName ? `, ${firstName}` : ""}.
          </h1>
          <p className="text-slate-100/84">
            Your best-fit roles, active applications, and profile momentum — all in one calm,
            fast workspace designed to keep you applying with intent.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <button onClick={() => navigate("/jobs")} className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-[13px] font-semibold text-[#1119d8] shadow-[0_18px_32px_-24px_rgba(15,23,42,0.8)] transition hover:-translate-y-0.5">
              <Sparkles size={14} /> Explore matches
            </button>
            <button onClick={() => navigate("/tracker")} className="inline-flex items-center gap-2 rounded-full border border-white/16 bg-white/8 px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-white/14">
              Open tracker
            </button>
          </div>
        </div>
      </section>

      <section className="metric-grid" aria-label="Job search summary">
        <Metric
          icon={BriefcaseBusiness}
          label="Jobs found"
          value={stats?.jobs_found ?? "—"}
          detail="Fresh matches and public search results →"
          onClick={() => navigate("/jobs")}
        />
        <Metric
          icon={Send}
          label="Applied"
          value={stats?.jobs_applied ?? "—"}
          detail="Track every role and follow-up →"
          onClick={() => navigate("/tracker")}
        />
        <Metric
          icon={Target}
          label="Target roles"
          value={roles.length || "—"}
          detail={roles.length ? roles.join(" · ") : "Complete your profile →"}
          onClick={() => navigate("/profile")}
        />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <QuickLink
          title="Refresh your profile fit"
          copy="Update skills, desired roles, or locations so recommendations stay sharp and relevant."
          action="Profile"
          onClick={() => navigate("/profile")}
        />
        <QuickLink
          title="Search beyond recommendations"
          copy="Need a broader sweep? Run manual India-wide searches by role, city, and work mode."
          action="Search"
          onClick={() => navigate("/jobs")}
        />
        <QuickLink
          title="Stay on top of recruiter mail"
          copy="Read job-related email, draft replies, and push interesting threads into your tracker."
          action="Inbox"
          onClick={() => navigate("/email-auto")}
        />
      </section>

      <section className="matches-section">
        <div className="section-heading gap-4">
          <div>
            <span className="editorial-kicker">Curated for you</span>
            <h2>Recent matches</h2>
          </div>
          <button onClick={() => navigate("/jobs")}>
            View all jobs <ArrowRight size={15} />
          </button>
        </div>
        {recent.length === 0 ? (
          <div className="glass-subtle editorial-empty rounded-[28px] border border-dashed border-border/80 bg-card/70">
            <h3>Nothing here yet — let’s sharpen your search.</h3>
            <p>Complete your profile, then run a search to discover roles across India.</p>
            <div>
              <button onClick={() => navigate("/profile")} className="btn-secondary !rounded-full">
                Complete profile
              </button>
              <button onClick={() => navigate("/jobs")} className="btn-primary !rounded-full">
                Explore jobs
              </button>
            </div>
          </div>
        ) : (
          <div className="job-grid">
            {recent.map((job) => (
              <JobMatchCard key={job.id ?? job.job_url} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
