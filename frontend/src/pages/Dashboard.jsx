import { useMemo, useState } from "react";
import { useMatches, useRefreshMatches } from "../hooks/useMatches";
import JobMatchCard from "../components/Dashboard/JobMatchCard";

const INDIA_LOCATIONS = [
  "All India", "Bengaluru", "Hyderabad", "Pune",
  "Mumbai", "Delhi NCR", "Chennai", "Remote",
];

const SCORE_FILTERS = [
  { label: "All scores", value: 0 },
  { label: "60%+", value: 60 },
  { label: "80%+", value: 80 },
];

export default function Dashboard() {
  const [location, setLocation] = useState("All India");
  const [minScore, setMinScore] = useState(0);
  const [sort, setSort] = useState("score"); // score | recent

  const { data: matches = [], isLoading, isError, refetch } = useMatches({
    location: location === "All India" ? undefined : location,
    minScore: minScore || undefined,
    sort,
  });
  const { mutate: refresh, isPending: refreshing } = useRefreshMatches();

  // Client-side guarantees on top of whatever the backend returns: enforce the
  // location chip, min-score floor, and sort order so the controls always work
  // even while the matching service is still being wired up.
  const visible = useMemo(() => {
    let rows = Array.isArray(matches) ? [...matches] : [];
    if (location !== "All India") {
      const needle = location.toLowerCase();
      rows = rows.filter((j) => {
        const loc = (j.location || "").toLowerCase();
        if (needle === "remote") return loc.includes("remote") || j.work_arrangement === "remote";
        return loc.includes(needle.split(" ")[0]);
      });
    }
    if (minScore) rows = rows.filter((j) => (j.match_score ?? 0) >= minScore);
    rows.sort((a, b) =>
      sort === "recent"
        ? new Date(b.posted_at || 0) - new Date(a.posted_at || 0)
        : (b.match_score ?? 0) - (a.match_score ?? 0)
    );
    return rows;
  }, [matches, location, minScore, sort]);

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      {/* Header */}
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Your matches</h1>
            <p className="text-[13px] text-slate-500 mt-0.5">
              Roles across India ranked against your profile — with why-fit, skill gaps & salary
            </p>
          </div>
          <button
            onClick={() => refresh(undefined, { onSettled: () => refetch() })}
            disabled={refreshing}
            className="btn-secondary text-[12.5px]"
            title="Re-run discovery + matching against your profile"
          >
            <svg className={`w-4 h-4 text-accent-600 ${refreshing ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {refreshing ? "Refreshing…" : "Refresh matches"}
          </button>
        </div>

        {/* India location chips */}
        <div className="flex flex-wrap items-center gap-1.5 mt-4">
          {INDIA_LOCATIONS.map((loc) => {
            const active = location === loc;
            return (
              <button
                key={loc}
                onClick={() => setLocation(loc)}
                className={`px-3 py-1.5 rounded-full text-[12px] font-semibold transition-all border ${
                  active
                    ? "bg-accent-600 text-white border-transparent"
                    : "bg-white/55 text-slate-600 border-slate-200/60 hover:text-slate-900 hover:border-accent-300"
                }`}
                style={active ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" } : undefined}
              >
                {loc}
              </button>
            );
          })}
        </div>

        {/* Score filter + sort */}
        <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
          <div className="inline-flex items-center gap-1 glass-subtle rounded-2xl p-1">
            {SCORE_FILTERS.map((f) => {
              const active = minScore === f.value;
              return (
                <button
                  key={f.value}
                  onClick={() => setMinScore(f.value)}
                  className={`relative px-3.5 py-1.5 rounded-xl text-[12px] font-semibold transition-all ${
                    active ? "text-white" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  {active && (
                    <span aria-hidden className="absolute inset-0 rounded-xl" style={{ background: "hsl(var(--primary))" }} />
                  )}
                  <span className="relative z-10">{f.label}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[12px] text-slate-500 font-medium">Sort by</span>
            <div className="inline-flex items-center gap-1 glass-subtle rounded-2xl p-1">
              {[
                { key: "score", label: "Best match" },
                { key: "recent", label: "Most recent" },
              ].map((s) => {
                const active = sort === s.key;
                return (
                  <button
                    key={s.key}
                    onClick={() => setSort(s.key)}
                    className={`px-3 py-1.5 rounded-xl text-[12px] font-semibold transition-all ${
                      active ? "bg-accent-600 text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                    style={active ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" } : undefined}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </header>

      {/* Feed */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6">
          {isLoading ? (
            <ul className="space-y-3">
              {[1, 2, 3, 4].map((i) => (
                <li key={i} className="h-40 glass-subtle rounded-2xl animate-pulse" />
              ))}
            </ul>
          ) : isError ? (
            <div className="glass-subtle rounded-2xl p-14 text-center">
              <p className="text-slate-800 font-semibold text-sm">Couldn't load your matches</p>
              <p className="text-slate-400 text-[12.5px] mt-1">The matching service may still be warming up.</p>
              <button onClick={() => refetch()} className="btn-secondary text-[12.5px] mt-4">Try again</button>
            </div>
          ) : visible.length === 0 ? (
            <div className="glass-subtle rounded-2xl p-14 text-center">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: "hsl(var(--muted))" }}>
                <svg className="w-7 h-7 text-accent-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z" />
                </svg>
              </div>
              <p className="text-slate-800 font-semibold text-sm">No matches yet</p>
              <p className="text-slate-400 text-[12.5px] mt-1 max-w-sm mx-auto">
                {location !== "All India" || minScore
                  ? "No roles fit these filters. Try widening your location or score."
                  : "Complete your profile and run a search profile, then refresh to see ranked matches."}
              </p>
              <div className="flex items-center justify-center gap-2 mt-4">
                <a href="/profile" className="btn-secondary text-[12.5px]">Complete profile</a>
                <a href="/job-preferences" className="btn-primary text-[12.5px]">Search profiles</a>
              </div>
            </div>
          ) : (
            <>
              <p className="text-[12px] text-slate-400 font-medium mb-3">
                {visible.length} {visible.length === 1 ? "match" : "matches"}
                {location !== "All India" && <> · {location}</>}
              </p>
              <ul className="space-y-3">
                {visible.map((job) => (
                  <JobMatchCard key={job.id ?? job.job_url} job={job} />
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
