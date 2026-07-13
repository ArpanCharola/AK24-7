import { useState } from "react";
import { Activity, BriefcaseBusiness, Database, Layers3, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useAdminAnalytics, useAdminRuns, useAdminWarehouse } from "../hooks/useAdminWarehouse";
import "./admin-console.css";

const EMPTY_ANALYTICS = { kpis: {}, daily: [], sources: [], roles: [], locations: [] };
const number = (value) => new Intl.NumberFormat("en-IN").format(value || 0);
const date = (value) => value ? new Date(value).toLocaleString("en-IN") : "Never";

function Notice({ query, label }) {
  if (query.isLoading) return <div className="admin-state">Loading {label}...</div>;
  if (!query.isError) return null;
  return <div className="admin-state admin-state--error"><ShieldAlert size={17} /> {label} is unavailable. The rest of admin remains usable.</div>;
}

function SparkBars({ rows }) {
  const max = Math.max(1, ...rows.map((row) => row.accepted_unique || row.count || 0));
  return <div className="admin-bars" aria-label="Daily accepted jobs chart">
    {rows.length ? rows.map((row) => <div className="admin-bar-wrap" key={row.date} title={`${row.date}: ${row.accepted_unique || row.count || 0}`}>
      <div className="admin-bar" style={{ height: `${Math.max(6, ((row.accepted_unique || row.count || 0) / max) * 100)}%` }} />
      <span>{String(row.date || "").slice(5)}</span>
    </div>) : <div className="admin-chart-empty">Daily totals appear after the first aggregation run.</div>}
  </div>;
}

function Breakdown({ title, rows, labelKey }) {
  return <article className="admin-panel"><header><div><h3>{title}</h3><p>Live jobs currently available</p></div></header><div className="admin-table-scroll"><table className="admin-data-table"><thead><tr><th>{labelKey === "role" ? "Role" : "Location"}</th><th>Jobs</th></tr></thead><tbody>{rows.map((row) => <tr key={row[labelKey]}><td>{row[labelKey]}</td><td>{number(row.count)}</td></tr>)}{!rows.length && <tr><td colSpan="2" className="admin-empty-cell">No coverage data yet.</td></tr>}</tbody></table></div></article>;
}

function SourceTable({ sources }) {
  return <article className="admin-panel"><header><div><h3>Source performance</h3><p>Raw sightings and clean warehouse contribution</p></div></header><div className="admin-table-scroll"><table className="admin-data-table"><thead><tr><th>Source</th><th>Raw</th><th>Accepted</th><th>Duplicates</th><th>Rejected</th><th>Live</th><th>Last success</th></tr></thead><tbody>{sources.map((s) => <tr key={s.source}><td><span className={`source-dot source-dot--${s.status || "unknown"}`}/>{s.source}</td><td>{number(s.raw_found)}</td><td>{number(s.accepted_unique)}</td><td>{number(s.duplicates)}</td><td>{number(s.rejected)}</td><td>{number(s.live_now)}</td><td>{date(s.last_success)}</td></tr>)}{!sources.length && <tr><td colSpan="7" className="admin-empty-cell">No source metrics yet.</td></tr>}</tbody></table></div></article>;
}

export function AnalyticsOverview() {
  const [range, setRange] = useState("today");
  const query = useAdminAnalytics(range);
  const data = query.data || EMPTY_ANALYTICS;
  const kpis = data.kpis || {};
  const cards = [
    ["Raw found today", kpis.raw_found_today, Activity],
    ["Accepted today", kpis.accepted_today, BriefcaseBusiness],
    ["Found yesterday", kpis.raw_found_yesterday, Layers3],
    ["Live jobs", kpis.live_jobs, Database],
    ["Duplicates today", kpis.duplicates_today, Layers3],
    ["Rejected today", kpis.rejected_today, ShieldAlert],
  ];
  return <section className="admin-view">
    <div className="admin-view-head"><div><p className="admin-eyebrow">ANALYTICS</p><h2>Aggregation overview</h2><p>Daily job ingestion, source health, recommendation coverage, roles, and locations.</p></div>
      <select value={range} onChange={(e) => setRange(e.target.value)}><option value="today">Today</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option></select>
    </div>
    <Notice query={query} label="Analytics" />
    <div className="admin-kpis">{cards.map(([label, value, Icon]) => <article key={label}><Icon size={18}/><span>{label}</span><strong>{number(value)}</strong></article>)}</div>
    <div className="admin-grid-2"><article className="admin-panel"><header><div><h3>Accepted jobs</h3><p>Unique roles admitted per day</p></div></header><SparkBars rows={data.daily || []}/></article>
      <article className="admin-panel"><header><div><h3>Recommendation coverage</h3><p>Profiles currently served</p></div></header><div className="admin-coverage"><strong>{number(kpis.profiles_with_matches)}</strong><span>profiles with matches</span><strong>{number(kpis.profiles_waiting)}</strong><span>waiting for coverage</span><strong>{kpis.recommendation_coverage_pct || 0}%</strong><span>coverage rate</span></div></article></div>
    <div className="admin-grid-2"><Breakdown title="Role coverage" labelKey="role" rows={data.roles || []}/><Breakdown title="Location coverage" labelKey="location" rows={data.locations || []}/></div>
    <SourceTable sources={data.sources || []}/>
  </section>;
}

export function JobWarehouse() {
  const [filters, setFilters] = useState({ page: 1, page_size: 25, q: "", role: "", location: "", time: "today", source: "", status: "live" });
  const query = useAdminWarehouse(filters);
  const data = query.data || { items: [], total: 0, page: filters.page, pages: 1 };
  const set = (key, value) => setFilters((old) => ({ ...old, [key]: value, page: key === "page" ? value : 1 }));
  return <section className="admin-view"><div className="admin-view-head"><div><p className="admin-eyebrow">CANONICAL RECORDS</p><h2>All jobs</h2><p>Every deduplicated job with source sightings and profile reach.</p></div><div className="admin-total">{number(data.total)}<span>jobs</span></div></div>
    <div className="admin-filters"><label><Search size={16}/><input value={filters.q} onChange={(e) => set("q", e.target.value)} placeholder="Title, employer, location..."/></label><input value={filters.role} onChange={(e) => set("role", e.target.value)} placeholder="Role"/><input value={filters.location} onChange={(e) => set("location", e.target.value)} placeholder="Location"/><select value={filters.time} onChange={(e) => set("time", e.target.value)}><option value="today">Today</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="90d">Last 90 days</option><option value="">All time</option></select><select value={filters.source} onChange={(e) => set("source", e.target.value)}><option value="">All sources</option>{["linkedin","naukri","indeed","wellfound","glassdoor","cutshort","instahyre","hirist","ats","warehouse"].map(x=><option key={x}>{x}</option>)}</select><select value={filters.status} onChange={(e) => set("status", e.target.value)}><option value="">All states</option><option value="live">Live</option><option value="quarantined">Quarantined</option><option value="expired">Expired</option><option value="closed">Closed</option></select></div>
    <Notice query={query} label="Job warehouse"/><article className="admin-panel"><div className="admin-table-scroll"><table className="admin-data-table admin-jobs-table"><thead><tr><th>Role</th><th>Location</th><th>Posted</th><th>Sources</th><th>Matches</th><th>Status</th></tr></thead><tbody>{(data.items || []).map((job) => <tr key={job.id}><td><strong>{job.title}</strong><small>{job.employer?.name || job.company || "Unknown employer"}</small></td><td>{job.location || "Unspecified"}<small>{job.work_arrangement || ""}</small></td><td>{job.posted_at ? new Date(job.posted_at).toLocaleDateString("en-IN") : "Unverified"}</td><td>{number(job.source_count || job.sources?.length)}</td><td>{number(job.matched_profiles)}</td><td><span className={`admin-status admin-status--${job.status}`}>{job.status}</span></td></tr>)}{!(data.items || []).length && <tr><td colSpan="6" className="admin-empty-cell">No jobs match these filters.</td></tr>}</tbody></table></div></article>
    <div className="admin-pagination"><button disabled={filters.page <= 1} onClick={() => set("page", filters.page - 1)}>Previous</button><span>Page {data.page || filters.page} of {data.pages || 1}</span><button disabled={filters.page >= (data.pages || 1)} onClick={() => set("page", filters.page + 1)}>Next</button></div>
  </section>;
}

export function SourceRuns() {
  const query = useAdminRuns(); const runs = query.data?.items || query.data?.runs || [];
  return <section className="admin-view"><div className="admin-view-head"><div><p className="admin-eyebrow">OPERATIONS</p><h2>Sources & runs</h2><p>Scheduler history, runtime, and partial source failures.</p></div><button className="admin-secondary" onClick={() => query.refetch()}><RefreshCw size={15}/> Refresh</button></div><Notice query={query} label="Run history"/><div className="admin-run-list">{runs.map((run) => <article key={run.id}><span className={`admin-status admin-status--${run.status}`}>{run.status}</span><div><strong>{run.trigger || "scheduled"} run #{run.id}</strong><small>{date(run.started_at)} - {run.duration_seconds ? `${run.duration_seconds}s` : "in progress"}</small></div><div><strong>{number(run.accepted_unique)}</strong><small>accepted</small></div><div><strong>{number(run.raw_found)}</strong><small>raw</small></div></article>)}{!runs.length && <div className="admin-state">No aggregation runs have been recorded.</div>}</div></section>;
}
