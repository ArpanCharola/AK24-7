/* Public unauthenticated job search.
 *
 * Anyone can hit this page (no token required), enter a role + location +
 * optional ATS source filter, and search the live SerpAPI feed. Results
 * are auto-saved to the shared JobPool. Logged-in users see an extra
 * "Import to profile" control on each card.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { publicJobsApi, jobSearchesApi } from "../services/api";

const SOURCES = [
  { value: "",                 label: "All sources" },
  // ATS — directly applyable
  { value: "greenhouse",       label: "Greenhouse" },
  { value: "ashby",            label: "Ashby" },
  { value: "workday",          label: "Workday" },
  { value: "icims",            label: "iCIMS" },
  { value: "smartrecruiters",  label: "SmartRecruiters" },
  { value: "bamboohr",         label: "BambooHR" },
  { value: "lever",            label: "Lever" },
  // Tier-2 portals
  { value: "amazon",           label: "Amazon" },
  { value: "netflix",          label: "Netflix" },
  { value: "microsoft",        label: "Microsoft" },
  { value: "apple",            label: "Apple" },
  { value: "google",           label: "Google" },
  { value: "meta",             label: "Meta" },
  // Company careers pages
  { value: "company_site",     label: "Company site (direct)" },
  // Aggregators — clickable, manual apply
  { value: "linkedin",         label: "LinkedIn" },
  { value: "indeed",           label: "Indeed" },
  { value: "glassdoor",        label: "Glassdoor" },
  { value: "ziprecruiter",     label: "ZipRecruiter" },
];

const DAYS = [
  { value: 1,  label: "Last 24 hours" },
  { value: 3,  label: "Last 3 days" },
  { value: 7,  label: "Last 7 days" },
  { value: 14, label: "Last 14 days" },
  { value: 30, label: "Last 30 days" },
];

const SOURCE_PILL = {
  greenhouse:      "bg-emerald-100/80 text-emerald-700 border-emerald-200/60",
  lever:           "bg-sky-100/80 text-sky-700 border-sky-200/60",
  ashby:           "bg-violet-100/80 text-violet-700 border-violet-200/60",
  workday:         "bg-amber-100/80 text-amber-700 border-amber-200/60",
  icims:           "bg-rose-100/80 text-rose-700 border-rose-200/60",
  smartrecruiters: "bg-indigo-100/80 text-indigo-700 border-indigo-200/60",
  bamboohr:        "bg-lime-100/80 text-lime-700 border-lime-200/60",
  amazon:          "bg-orange-100/80 text-orange-700 border-orange-200/60",
  netflix:         "bg-rose-100/80 text-rose-700 border-rose-200/60",
  microsoft:       "bg-sky-100/80 text-sky-700 border-sky-200/60",
  apple:           "bg-slate-100/80 text-slate-700 border-slate-200/60",
  google:          "bg-blue-100/80 text-blue-700 border-blue-200/60",
  meta:            "bg-blue-100/80 text-blue-700 border-blue-200/60",
  company_site:    "bg-teal-100/80 text-teal-700 border-teal-200/60",
  linkedin:        "bg-sky-100/80 text-sky-700 border-sky-200/60",
  indeed:          "bg-blue-100/80 text-blue-700 border-blue-200/60",
  glassdoor:       "bg-emerald-100/80 text-emerald-700 border-emerald-200/60",
  ziprecruiter:    "bg-indigo-100/80 text-indigo-700 border-indigo-200/60",
};

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const MODES = [
  { value: "live",  label: "Live Search" },
  { value: "pool",  label: "Recent Pool (24h)" },
];

const PER_PAGE = 10;  // jobs shown per page

export default function PublicJobs() {
  const hasToken = !!localStorage.getItem("token");
  const navigate = useNavigate();

  const [mode, setMode] = useState("live");          // "live" | "pool"
  const [role, setRole] = useState("Software Engineer");
  const [location, setLocation] = useState("India");
  const [source, setSource] = useState("");
  const [postedWithinDays, setPostedWithinDays] = useState(7);
  const [pages, setPages] = useState(5);

  const [results, setResults] = useState([]);
  const [page, setPage] = useState(1);              // 1-based current page
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  // For the "Import to profile" UX
  const [profiles, setProfiles] = useState([]);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [importingFor, setImportingFor] = useState(null);
  const [importMsg, setImportMsg] = useState(null);

  useEffect(() => {
    if (!hasToken) return;
    jobSearchesApi.list().then((r) => setProfiles(r.data || [])).catch(() => {});
  }, [hasToken]);

  // When user lands on the Pool tab, auto-load the pool browse.
  useEffect(() => {
    if (mode !== "pool") return;
    loadPool();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  async function loadPool() {
    setLoading(true);
    setErr(null);
    setSelectedIds(new Set());
    setImportMsg(null);
    try {
      const r = await publicJobsApi.browse({
        role: role.trim() || undefined,
        source: source || undefined,
        limit: 200,
      });
      setResults(r.data || []);
      setPage(1);
      setMeta({ matched: (r.data || []).length, fetched: (r.data || []).length, saved: 0, query: role });
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "Couldn't load the pool.");
      setResults([]);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  }

  async function runSearch(e) {
    e?.preventDefault?.();
    if (!role.trim()) return;
    setLoading(true);
    setErr(null);
    setSelectedIds(new Set());
    setImportMsg(null);
    try {
      const r = await publicJobsApi.search({
        role: role.trim(),
        location: location.trim() || "India",
        source: source || undefined,
        postedWithinDays,
        pages,
      });
      setResults(r.data.jobs || []);
      setPage(1);
      setMeta({
        fetched: r.data.fetched,
        matched: r.data.matched,
        saved: r.data.saved,
        query: r.data.query,
      });
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "Search failed.");
      setResults([]);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  }

  const allChecked = useMemo(
    () => results.length > 0 && selectedIds.size === results.length,
    [results, selectedIds],
  );

  // Pagination — 10 jobs per page, computed from the already-loaded results.
  const pageCount = Math.max(1, Math.ceil(results.length / PER_PAGE));
  const safePage = Math.min(page, pageCount);
  const pageItems = useMemo(
    () => results.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE),
    [results, safePage],
  );

  function toggleAll() {
    if (allChecked) setSelectedIds(new Set());
    else setSelectedIds(new Set(results.map((j) => j.id)));
  }
  function toggleOne(id) {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelectedIds(next);
  }

  async function handleImport(profileId) {
    const ids = Array.from(selectedIds);
    if (!ids.length) return;
    setImportingFor(profileId);
    setImportMsg(null);
    try {
      const r = await publicJobsApi.importToProfile(profileId, ids);
      const { imported, already_present, skipped_filters, requested } = r.data;
      const lines = [`Imported ${imported} of ${requested}`];
      if (already_present) lines.push(`${already_present} already in your feed`);
      if (skipped_filters) lines.push(`${skipped_filters} didn't pass profile filters`);
      setImportMsg(lines.join(" · "));
      setSelectedIds(new Set());
    } catch (e) {
      setImportMsg(e?.response?.data?.detail || "Import failed.");
    } finally {
      setImportingFor(null);
    }
  }

  return (
    <div className="min-h-screen" style={{ background: "hsl(var(--background))" }}>
      {/* Minimal top bar — works without auth */}
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <Link to={hasToken ? "/" : "/jobs"} className="font-bold tracking-tight text-slate-900">
          AK24/7Jobs
          <span className="ml-2 text-[12px] font-medium text-slate-500">/ Public Jobs</span>
        </Link>
        <div className="flex items-center gap-3 text-[13px]">
          {hasToken ? (
            <button onClick={() => navigate("/")} className="text-slate-600 hover:text-slate-900">
              Dashboard →
            </button>
          ) : (
            <Link to="/login" className="btn-primary !py-1.5 !px-3 text-[12.5px]">
              Sign in to save
            </Link>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-[28px] font-bold tracking-tight text-slate-900">Public job pool</h1>
        <p className="text-[14px] text-slate-500 mt-1.5">
          Search live across Greenhouse, Ashby, Workday, iCIMS, SmartRecruiters, BambooHR, Amazon, Netflix.
          Results are saved to a shared pool for 24 hours. Logged-in users can import matching jobs into their personal feed.
        </p>

        {/* Mode toggle: live search vs browse-already-stored pool */}
        <div className="mt-5 inline-flex gap-1 p-1 rounded-xl border border-slate-200/70 bg-white/40">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              className={`px-3 py-1.5 rounded-lg text-[12.5px] font-medium transition-colors ${
                mode === m.value
                  ? "bg-accent-500 text-white shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {m.label}
            </button>
          ))}
          {mode === "pool" && (
            <button
              type="button"
              onClick={loadPool}
              disabled={loading}
              className="ml-2 px-3 py-1.5 text-[12px] text-slate-500 hover:text-slate-900 disabled:opacity-60"
              title="Reload pool"
            >
              ↻ Refresh
            </button>
          )}
        </div>

        {/* Search form — only shown in live mode */}
        {mode === "live" && (
        <form onSubmit={runSearch} className="mt-6 glass rounded-2xl p-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[220px]">
            <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Role</label>
            <input
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="Software Engineer"
              className="input-glass mt-1.5"
              required
            />
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Location</label>
            <input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="India"
              className="input-glass mt-1.5"
            />
          </div>
          <div className="min-w-[140px]">
            <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Source</label>
            <select value={source} onChange={(e) => setSource(e.target.value)} className="input-glass mt-1.5">
              {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div className="min-w-[140px]">
            <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Posted</label>
            <select
              value={postedWithinDays}
              onChange={(e) => setPostedWithinDays(Number(e.target.value))}
              className="input-glass mt-1.5"
            >
              {DAYS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
            </select>
          </div>
          <div className="min-w-[120px]">
            <label
              className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider"
              title="Each page ≈ 10 jobs and costs 1 SerpAPI credit"
            >
              Depth
            </label>
            <select
              value={pages}
              onChange={(e) => setPages(Number(e.target.value))}
              className="input-glass mt-1.5"
            >
              {[1, 2, 5, 10].map((n) => (
                <option key={n} value={n}>
                  {n} page{n > 1 ? "s" : ""} (~{n * 10} jobs)
                </option>
              ))}
            </select>
          </div>
          <button type="submit" disabled={loading} className="btn-primary text-[13px] disabled:opacity-60">
            {loading ? "Searching…" : "Search"}
          </button>
        </form>
        )}

        {/* Pool-mode mini filter bar */}
        {mode === "pool" && (
          <form
            onSubmit={(e) => { e.preventDefault(); loadPool(); }}
            className="mt-6 glass rounded-2xl p-4 flex flex-wrap items-end gap-3"
          >
            <div className="flex-1 min-w-[220px]">
              <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Filter by role (title substring)</label>
              <input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="(leave blank for all)"
                className="input-glass mt-1.5"
              />
            </div>
            <div className="min-w-[160px]">
              <label className="text-[11.5px] font-semibold text-slate-600 uppercase tracking-wider">Source</label>
              <select value={source} onChange={(e) => setSource(e.target.value)} className="input-glass mt-1.5">
                {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <button type="submit" disabled={loading} className="btn-primary text-[13px] disabled:opacity-60">
              {loading ? "Loading…" : "Apply filters"}
            </button>
          </form>
        )}

        {err && (
          <p className="mt-4 text-[12.5px] text-rose-700 bg-rose-50/80 border border-rose-200/60 rounded-xl px-4 py-3">
            {err}
          </p>
        )}

        {meta && !err && mode === "live" && (
          <p className="mt-4 text-[12.5px] text-slate-500">
            Found {meta.matched} matching jobs (from {meta.fetched} fetched, {meta.saved} saved to pool).
          </p>
        )}
        {meta && !err && mode === "pool" && (
          <p className="mt-4 text-[12.5px] text-slate-500">
            Showing {meta.matched} jobs from the shared pool (added in the last 24 hours).
          </p>
        )}

        {/* Bulk-import toolbar (logged-in only) */}
        {hasToken && results.length > 0 && (
          <div className="mt-4 glass rounded-2xl p-3 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[12.5px] text-slate-700 cursor-pointer">
              <input type="checkbox" checked={allChecked} onChange={toggleAll} />
              <span className="font-medium">
                {selectedIds.size > 0 ? `${selectedIds.size} selected` : "Select all"}
              </span>
            </label>
            {selectedIds.size > 0 && profiles.length > 0 && (
              <>
                <span className="text-slate-400 text-[12px]">→</span>
                <span className="text-[12.5px] text-slate-600">Import to:</span>
                {profiles.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handleImport(p.id)}
                    disabled={importingFor === p.id}
                    className="btn-secondary !py-1 !px-2.5 text-[11.5px]"
                  >
                    {importingFor === p.id ? "Importing…" : p.name}
                  </button>
                ))}
              </>
            )}
            {selectedIds.size > 0 && profiles.length === 0 && (
              <span className="text-[12px] text-slate-500">
                No profiles yet — <Link to="/job-preferences" className="text-accent-600 hover:underline">create one</Link>.
              </span>
            )}
            {importMsg && <span className="text-[12px] text-emerald-700 ml-auto">{importMsg}</span>}
          </div>
        )}

        {/* Results */}
        <ul className="mt-5 space-y-3">
          {pageItems.map((j) => (
            <li key={j.id} className="glass rounded-2xl p-4 flex items-start gap-3">
              {hasToken && (
                <input
                  type="checkbox"
                  checked={selectedIds.has(j.id)}
                  onChange={() => toggleOne(j.id)}
                  className="mt-1.5"
                />
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center flex-wrap gap-2">
                  <h3 className="text-[14.5px] font-semibold text-slate-900">{j.title || "(untitled)"}</h3>
                  <span className={`pill border capitalize ${SOURCE_PILL[j.source] || "bg-slate-100/80 text-slate-600 border-slate-200/60"}`}>
                    {j.source}
                  </span>
                  {j.work_arrangement && j.work_arrangement !== "unknown" && (
                    <span className="pill bg-slate-100/80 text-slate-600 border border-slate-200/60 capitalize">
                      {j.work_arrangement}
                    </span>
                  )}
                </div>
                <p className="text-[12.5px] text-slate-500 mt-1">
                  <span className="font-semibold text-slate-700">{j.company || "—"}</span>
                  {j.location && <> · {j.location}</>}
                  {j.posted_at && <span className="text-slate-400 ml-2">· {fmtDate(j.posted_at)}</span>}
                </p>
                <a
                  href={j.job_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11.5px] text-accent-600 hover:text-accent-700 hover:underline mt-1.5 inline-flex items-center gap-1 max-w-full truncate"
                >
                  <span className="truncate">{j.job_url}</span>
                </a>
              </div>
            </li>
          ))}
          {!loading && !results.length && meta && mode === "live" && (
            <li className="text-center text-[13px] text-slate-500 py-8">
              No matching jobs in this search. Try a broader role or a different source.
            </li>
          )}
          {!loading && !results.length && meta && mode === "pool" && (
            <li className="text-center text-[13px] text-slate-500 py-8">
              Nothing in the pool matches these filters. Try a different role / source,
              or switch to Live Search to populate the pool.
            </li>
          )}
          {!loading && !results.length && !meta && (
            <li className="text-center text-[13px] text-slate-400 py-8">
              {mode === "live"
                ? "Enter a role and click Search to begin."
                : "Loading recent pool…"}
            </li>
          )}
        </ul>

        {/* Pagination — 10 jobs per page */}
        {results.length > PER_PAGE && (
          <nav className="mt-6 flex items-center justify-center gap-1.5 flex-wrap">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              className="px-3 py-1.5 rounded-lg text-[12.5px] font-medium glass-subtle text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed hover:text-slate-900"
            >
              ← Prev
            </button>
            {Array.from({ length: pageCount }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === pageCount || Math.abs(p - safePage) <= 1)
              .reduce((acc, p) => {
                // insert an ellipsis marker when there's a gap
                if (acc.length && p - acc[acc.length - 1] > 1) acc.push("…");
                acc.push(p);
                return acc;
              }, [])
              .map((p, idx) =>
                p === "…" ? (
                  <span key={`gap-${idx}`} className="px-1.5 text-slate-400 text-[12.5px]">…</span>
                ) : (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPage(p)}
                    className={`min-w-[34px] px-2.5 py-1.5 rounded-lg text-[12.5px] font-medium transition-colors ${
                      p === safePage
                        ? "bg-accent-500 text-white shadow-sm"
                        : "glass-subtle text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {p}
                  </button>
                )
              )}
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              disabled={safePage >= pageCount}
              className="px-3 py-1.5 rounded-lg text-[12.5px] font-medium glass-subtle text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed hover:text-slate-900"
            >
              Next →
            </button>
          </nav>
        )}
        {results.length > 0 && (
          <p className="mt-3 text-center text-[11.5px] text-slate-400">
            Showing {(safePage - 1) * PER_PAGE + 1}–{Math.min(safePage * PER_PAGE, results.length)} of {results.length}
          </p>
        )}
      </main>
    </div>
  );
}
