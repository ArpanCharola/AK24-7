import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BriefcaseBusiness, Send, Target, ArrowRight } from "lucide-react";
import { useEffect } from "react";
import { authApi } from "../services/api";
import { useDashboardStats } from "../hooks/useDashboard";
import { useMatches } from "../hooks/useMatches";
import JobMatchCard from "../components/Jobs/JobMatchCard";

function Metric({ icon: Icon, label, value, detail, onClick }) {
  return <button onClick={onClick} className="glass metric-card group">
    <div className="metric-label"><span>{label}</span><Icon size={19}/></div>
    <strong>{value}</strong><span className="metric-detail">{detail}</span>
  </button>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: me } = useQuery({ queryKey:["me"], queryFn:()=>authApi.me().then(r=>r.data), staleTime:300000 });
  const { data: stats } = useDashboardStats();
  const { data: matches = [] } = useMatches({ sort:"recent" });
  useEffect(() => {
    if (me?.is_admin) navigate("/admin", { replace: true });
  }, [me?.is_admin, navigate]);
  if (me?.is_admin) {
    return null;
  }
  const roles = stats?.target_roles || [];
  const recent = (Array.isArray(matches) ? matches : []).slice(0,6);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const firstName = (me?.full_name || me?.username || "").trim().split(" ")[0];

  return <div className="page-wrap dashboard-page">
    <section className="dashboard-hero">
      <div className="hero-copy">
        <span className="editorial-kicker">Your career desk · updated today</span>
        <h1>{greeting}{firstName ? `, ${firstName}` : ""}.</h1>
        <p>Here’s your job search at a glance—focused, current, and ready for your next move.</p>
      </div>
    </section>

    <section className="metric-grid" aria-label="Job search summary">
      <Metric icon={BriefcaseBusiness} label="Jobs found" value={stats?.jobs_found ?? "—"} detail="View all jobs →" onClick={()=>navigate("/jobs")}/>
      <Metric icon={Send} label="Applied" value={stats?.jobs_applied ?? "—"} detail="Open tracker →" onClick={()=>navigate("/tracker")}/>
      <Metric icon={Target} label="Target roles" value={roles.length || "—"} detail={roles.length ? roles.join(" · ") : "Set in profile →"} onClick={()=>navigate("/profile")}/>
    </section>

    <section className="matches-section">
      <div className="section-heading"><div><span className="editorial-kicker">Curated for you</span><h2>Recent matches</h2></div>
        <button onClick={()=>navigate("/jobs")}>View all jobs <ArrowRight size={15}/></button></div>
      {recent.length === 0 ? <div className="glass-subtle editorial-empty">
        <h3>Nothing here yet—let’s sharpen your search.</h3><p>Complete your profile, then run a search to discover roles across India.</p>
        <div><button onClick={()=>navigate("/profile")} className="btn-secondary">Complete profile</button><button onClick={()=>navigate("/jobs")} className="btn-primary">Explore jobs</button></div>
      </div> : <div className="job-grid">{recent.map(job=><JobMatchCard key={job.id ?? job.job_url} job={job}/>)}</div>}
    </section>
  </div>;
}
