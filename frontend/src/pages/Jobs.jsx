import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Search, SlidersHorizontal, Sparkles } from "lucide-react";
import { apiErrorMessage, matchesApi, publicJobsApi } from "../services/api";
import { useProfile } from "../hooks/useProfile";
import JobMatchCard from "../components/Jobs/JobMatchCard";
import ProfileGate from "../components/Profile/ProfileGate";
import { INDIA_LOCATION_OPTIONS, WORK_MODE_FILTERS } from "../lib/india-cities";

const FRESHNESS = [
  { label: "Any time", value: "" },
  { label: "24 hours", value: "1" },
  { label: "3 days", value: "3" },
  { label: "7 days", value: "7" },
];

const EXPERIENCE_OPTIONS = [
  { label: "Fresher / entry level", value: "fresher" },
  { label: "Junior", value: "junior" },
  { label: "Mid-level", value: "mid" },
  { label: "Senior", value: "senior" },
];

const SEARCH_LOCATION_OPTIONS = ["India", ...INDIA_LOCATION_OPTIONS];

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.filter(Boolean);
  } catch {
    // legacy CSV
  }
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function profileExperience(profile) {
  const months = Number(profile?.experience_months || 0) + Number(profile?.experience_years || 0) * 12;
  if (months <= 12) return "fresher";
  if (months <= 36) return "junior";
  if (months <= 72) return "mid";
  return "senior";
}

function hasProfileExperience(profile) {
  return profile?.experience_years != null || profile?.experience_months != null;
}

function hasRecommendationProfile(profile) {
  if (typeof profile?.recommendation_ready === "boolean") return profile.recommendation_ready;
  const desiredRoles = asList(profile?.desired_roles);
  const locations = asList(profile?.preferred_locations);
  const skills = asList(profile?.skills);
  const hasProfileBase = Boolean(profile?.resume_text) || (skills.length > 0 && hasProfileExperience(profile));
  return Boolean(
    hasProfileBase && desiredRoles.length > 0 && locations.length > 0
  );
}

function SearchLocationPicker({ value, onChange }) {
  const [needle, setNeedle] = useState("");
  const selected = value.length ? value : ["India"];
  const visible = SEARCH_LOCATION_OPTIONS.filter((item) => item.toLowerCase().includes(needle.trim().toLowerCase()));
  const remoteVisible = visible.filter((item) => ["India", "Remote India", "Pan India"].includes(item));
  const cityVisible = visible.filter((item) => !["India", "Remote India", "Pan India"].includes(item));

  function toggle(item) {
    if (item === "India") {
      onChange(["India"]);
      return;
    }
    const withoutIndia = selected.filter((current) => current !== "India");
    if (withoutIndia.includes(item)) {
      const next = withoutIndia.filter((current) => current !== item);
      onChange(next.length ? next : ["India"]);
      return;
    }
    onChange([...withoutIndia, item]);
  }

  return (
    <div className="rounded-[24px] border border-border bg-card/80 p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap gap-1.5">
        {selected.map((item) => (
          <span key={item} className="pill pill-brand">
            {item}
          </span>
        ))}
      </div>
      <label className="input-glass mb-3 flex items-center gap-2 !py-2.5">
        <Search size={14} className="shrink-0 text-muted-foreground" />
        <input
          value={needle}
          onChange={(event) => setNeedle(event.target.value)}
          placeholder="Search India locations..."
          className="flex-1 bg-transparent text-[13px] text-foreground outline-none"
        />
      </label>
      <div className="max-h-52 space-y-3 overflow-y-auto pr-1">
        {remoteVisible.length > 0 && (
          <div>
            <p className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              National / Remote
            </p>
            <div className="grid grid-cols-2 gap-1 md:grid-cols-3">
              {remoteVisible.map((item) => (
                <label key={item} className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-2 text-[12px] transition-colors hover:bg-muted">
                  <input type="checkbox" checked={selected.includes(item)} onChange={() => toggle(item)} className="accent-brand" />
                  <span className="truncate">{item === "India" ? "All India" : item}</span>
                </label>
              ))}
            </div>
          </div>
        )}
        {cityVisible.length > 0 && (
          <div>
            <p className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cities</p>
            <div className="grid grid-cols-2 gap-1 md:grid-cols-3 xl:grid-cols-4">
              {cityVisible.map((item) => (
                <label key={item} className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-2 text-[12px] transition-colors hover:bg-muted">
                  <input type="checkbox" checked={selected.includes(item)} onChange={() => toggle(item)} className="accent-brand" />
                  <span className="truncate">{item}</span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function JobsTopHero({ mode, setMode, profileReady, searchedJobsCount }) {
  return (
    <section className="rounded-[32px] border border-white/10 bg-[linear-gradient(135deg,#0f2ea8_0%,#253dce_52%,#6d28d9_140%)] px-6 py-7 text-white shadow-[0_30px_90px_-46px_rgba(37,61,206,0.52)] md:px-8 md:py-8">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl">
          <span className="inline-flex rounded-full border border-white/14 bg-white/8 px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-white/82">Discovery desk · recommendations + cached India search</span>
          <h1 className="mt-3 text-[clamp(2rem,4vw,3.5rem)] font-semibold leading-[1.02] tracking-tight text-white">
            Find the roles worth your next application.
          </h1>
          <p className="mt-3 max-w-xl text-[14px] leading-7 text-slate-100/84">
            Use profile-based recommendations when your setup is ready, or search the shared warehouse instantly without waiting on live scraping.
          </p>
        </div>
        <div className="inline-flex w-fit rounded-2xl border border-white/12 bg-white/10 p-1.5 shadow-sm backdrop-blur-sm">
          <button
            type="button"
            onClick={() => setMode("recommended")}
            className={`rounded-xl px-4 py-2 text-[12px] font-semibold transition-colors ${mode === "recommended" ? "bg-white text-[#0f2ea8] shadow-sm" : "text-white/72"}`}
          >
            Recommended {profileReady ? "ready" : "setup"}
          </button>
          <button
            type="button"
            onClick={() => setMode("search")}
            className={`rounded-xl px-4 py-2 text-[12px] font-semibold transition-colors ${mode === "search" ? "bg-white text-[#0f2ea8] shadow-sm" : "text-white/72"}`}
          >
            Search jobs {searchedJobsCount ? `(${searchedJobsCount})` : ""}
          </button>
        </div>
      </div>
    </section>
  );
}

export default function Jobs() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const refreshFromProfile = searchParams.get("refresh") === "1";
  const autoRefreshRef = useRef(false);
  const searchDefaultsSeededRef = useRef(false);
  const [mode, setMode] = useState("recommended");

  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const [location, setLocation] = useState("");
  const [freshness, setFreshness] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [experience, setExperience] = useState("");

  const [searchRole, setSearchRole] = useState("");
  const [searchLocations, setSearchLocations] = useState(["India"]);
  const [searchExperience, setSearchExperience] = useState("fresher");
  const [searchWorkMode, setSearchWorkMode] = useState("");
  const [searchFreshness, setSearchFreshness] = useState("7");
  const [searchRan, setSearchRan] = useState(false);

  const { data: profile, isLoading: profileLoading, isError: profileError } = useProfile();
  const locations = useMemo(() => asList(profile?.preferred_locations), [profile?.preferred_locations]);
  const desiredRoles = useMemo(() => asList(profile?.desired_roles), [profile?.desired_roles]);
  const profileSkills = useMemo(() => asList(profile?.skills), [profile?.skills]);
  const profileReady = hasRecommendationProfile(profile);
  const activeMode = !profileLoading && !profileReady && mode === "recommended" ? "search" : mode;
  const defaultExperience = profileExperience(profile);

  useEffect(() => {
    if (!profile) return;
    if (!experience) setExperience(defaultExperience);
    if (!searchExperience) setSearchExperience(defaultExperience);
    if (searchDefaultsSeededRef.current) return;
    if (desiredRoles.length) setSearchRole(desiredRoles[0]);
    setSearchLocations(["India"]);
    searchDefaultsSeededRef.current = true;
  }, [defaultExperience, desiredRoles, experience, locations, profile, searchExperience]);

  const hasProfileBase = Boolean(profile?.resume_text) || (profileSkills.length > 0 && hasProfileExperience(profile));
  const completed = profile?.recommendation_completed ?? ((hasProfileBase ? 1 : 0) + (desiredRoles.length > 0 ? 1 : 0) + (locations.length > 0 ? 1 : 0));

  const filters = {
    role: role || undefined,
    location: location || undefined,
    experience: experience || defaultExperience,
    workArrangement: workMode || undefined,
    postedWithinDays: freshness || undefined,
    sort: "score",
    limit: 50,
  };

  const refresh = useMutation({
    mutationFn: () => matchesApi.refresh().then((response) => response.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["matches"] }),
  });

  useEffect(() => {
    if (!profileReady || !refreshFromProfile || autoRefreshRef.current) return;
    autoRefreshRef.current = true;
    setMode("recommended");
    refresh.mutate(undefined, {
      onSettled: () => setSearchParams({}, { replace: true }),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileReady, refreshFromProfile]);

  const matchesQuery = useQuery({
    queryKey: ["matches", filters],
    enabled: profileReady,
    queryFn: () => matchesApi.feed(filters).then((response) => response.data),
    staleTime: 60000,
  });

  // Server-side filtering + true pagination. The backend now filters by city
  // (CSV) and India-confidence and paginates in SQL, so we page by offset and
  // append — no client-side location filtering over a single page.
  const SEARCH_PAGE = 50;
  const [searchJobs, setSearchJobs] = useState([]);
  const [searchOffset, setSearchOffset] = useState(0);
  const [searchHasMore, setSearchHasMore] = useState(false);

  const searchMutation = useMutation({
    mutationFn: async ({ offset = 0 } = {}) => {
      const requested = searchLocations.length ? searchLocations : ["India"];
      // "India" means no city narrowing; otherwise pass the real CSV selection.
      const locationParam = requested.includes("India") ? undefined : requested.join(",");
      const response = await publicJobsApi.browse({
        role: searchRole || undefined,
        location: locationParam,
        experience: searchExperience,
        workArrangement: searchWorkMode || undefined,
        postedWithinDays: searchFreshness || 7,
        limit: SEARCH_PAGE,
        offset,
      });
      return { page: response.data || [], offset };
    },
    onSuccess: ({ page, offset }) => {
      setSearchJobs((prev) => {
        if (offset === 0) return page;
        const seen = new Set(prev.map((j) => j.job_url || j.id));
        return [...prev, ...page.filter((j) => !seen.has(j.job_url || j.id))];
      });
      setSearchOffset(offset + page.length);
      setSearchHasMore(page.length === SEARCH_PAGE);
      setSearchRan(true);
    },
  });

  const searchedJobs = searchJobs;

  const visibleRecommended = useMemo(() => {
    const recommendedJobs = Array.isArray(matchesQuery.data) ? matchesQuery.data : [];
    const needle = query.trim().toLowerCase();
    if (!needle) return recommendedJobs;
    return recommendedJobs.filter((job) => [job.title, job.company, job.location].some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [matchesQuery.data, query]);

  function resetFilters() {
    setQuery("");
    setRole("");
    setLocation("");
    setFreshness("");
    setWorkMode("");
    setExperience(defaultExperience);
  }

  function runSearch(event) {
    event.preventDefault();
    // Role is optional now — a bare city/experience browse is valid supply.
    setSearchJobs([]);
    setSearchOffset(0);
    setSearchHasMore(false);
    searchMutation.mutate({ offset: 0 });
  }

  function loadMoreSearch() {
    searchMutation.mutate({ offset: searchOffset });
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-6 md:px-8">
      <JobsTopHero mode={activeMode} setMode={setMode} profileReady={profileReady} searchedJobsCount={searchedJobs.length} />

      {profileLoading ? (
        <div className="glass-subtle h-16 animate-pulse rounded-2xl" />
      ) : profileError ? (
        <div className="rounded-2xl border border-warning/40 bg-warning/10 px-4 py-3 text-[13px] text-warning">
          Sign in again to load recommendations from your profile. Search still works from the Search Jobs tab.
        </div>
      ) : activeMode === "recommended" ? (
        <ProfileGate completed={completed} required={3} />
      ) : null}

      {activeMode === "recommended" && !profileLoading && profileReady && (
        <>
          <section className="glass-subtle rounded-[28px] p-4 md:p-5" aria-label="Recommended job filters">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Recommended Jobs</h2>
                <p className="mt-1 text-[12px] leading-6 text-muted-foreground">
                  Uses your saved resume, desired roles, preferred locations, and experience.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={() => refresh.mutate()} disabled={refresh.isPending} className="btn-secondary !rounded-full !px-3 !py-2 text-[12px]">
                  <RefreshCw size={14} className={refresh.isPending ? "animate-spin" : ""} />
                  {refresh.isPending ? "Refreshing" : "Refresh jobs"}
                </button>
                <button type="button" onClick={resetFilters} className="btn-ghost !rounded-full text-[12px] font-semibold text-brand">
                  Clear filters
                </button>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
              <label className="input-glass flex items-center gap-2 !py-2.5 xl:col-span-2">
                <Search size={14} className="shrink-0 text-muted-foreground" />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title or company..." className="flex-1 bg-transparent text-[13px] text-foreground outline-none" />
              </label>
              <input className="input-glass !py-2.5" value={role} onChange={(event) => setRole(event.target.value)} placeholder="Role filter" />
              <select className="input-glass !py-2.5" value={experience || defaultExperience} onChange={(event) => setExperience(event.target.value)}>
                {EXPERIENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select className="input-glass !py-2.5" value={location} onChange={(event) => setLocation(event.target.value)}>
                <option value="">All desired locations</option>
                {locations.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <select className="input-glass !py-2.5" value={workMode} onChange={(event) => setWorkMode(event.target.value)}>
                {WORK_MODE_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <label className="inline-flex items-center gap-2 text-[12px] text-muted-foreground">
                <SlidersHorizontal size={14} />
                <select className="input-glass !w-full !py-2.5" value={freshness} onChange={(event) => setFreshness(event.target.value)}>
                  {FRESHNESS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          <div className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-muted-foreground">
            <p className="tnum">
              {visibleRecommended.length} recommended job{visibleRecommended.length === 1 ? "" : "s"}
              {matchesQuery.isFetching || refresh.isPending ? " · updating" : ""}
            </p>
            {(refresh.isPending || refresh.data) && (
              <div className="rounded-full border border-border bg-card/70 px-3 py-1.5">
                {refresh.isPending
                  ? "Refreshing recommendations from your latest profile..."
                  : `Last refresh found ${refresh.data?.returned || visibleRecommended.length || 0} recommendation${(refresh.data?.returned || visibleRecommended.length || 0) === 1 ? "" : "s"}.`}
              </div>
            )}
          </div>

          {matchesQuery.isLoading ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="glass h-40 rounded-3xl animate-pulse" />
              ))}
            </div>
          ) : visibleRecommended.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-border bg-card/60 py-16 text-center">
              <Search size={40} strokeWidth={1} className="mb-3 text-muted-foreground/40" />
              <p className="text-sm font-semibold">No profile-fit recommendations yet</p>
              <p className="mt-1 max-w-md text-[12.5px] text-muted-foreground">
                We are filtering by desired location and experience. Use Search Jobs for a manual role/location search.
              </p>
            </div>
          ) : (
            <div className="job-grid">
              {visibleRecommended.map((job) => (
                <JobMatchCard key={job.id ?? job.job_url} job={job} />
              ))}
            </div>
          )}
        </>
      )}

      {activeMode === "search" && (
        <>
          <form onSubmit={runSearch} className="glass-subtle rounded-[28px] p-4 md:p-5" aria-label="Manual job search">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Search Jobs</h2>
                <p className="mt-1 text-[12px] leading-6 text-muted-foreground">
                  Search the cached shared job warehouse by role, experience, location, and work mode — independent of your saved recommendations.
                </p>
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/70 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-brand">
                <Sparkles size={12} /> Warehouse search
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
              <input className="input-glass !py-2.5 xl:col-span-2" value={searchRole} onChange={(event) => setSearchRole(event.target.value)} placeholder="Job role, e.g. Software Engineer" />
              <select className="input-glass !py-2.5" value={searchExperience} onChange={(event) => setSearchExperience(event.target.value)}>
                {EXPERIENCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select className="input-glass !py-2.5" value={searchWorkMode} onChange={(event) => setSearchWorkMode(event.target.value)}>
                {WORK_MODE_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select className="input-glass !py-2.5" value={searchFreshness} onChange={(event) => setSearchFreshness(event.target.value)}>
                {FRESHNESS.filter((option) => option.value !== "").map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-4">
              <SearchLocationPicker value={searchLocations} onChange={setSearchLocations} />
            </div>

            <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <p className="text-[12px] text-muted-foreground">
                Start with All India for maximum supply, then narrow by city or remote preference only if needed.
              </p>
              <button type="submit" disabled={searchMutation.isPending || !searchRole.trim()} className="btn-gradient w-full !rounded-full !px-5 !py-2.5 text-[12px] md:w-auto">
                <Search size={14} />
                {searchMutation.isPending ? "Searching" : "Search jobs"}
              </button>
            </div>
          </form>

          <div className="flex flex-wrap items-center justify-between gap-3 text-[12px] text-muted-foreground">
            <p className="tnum">
              {searchRan ? `${searchedJobs.length} search result${searchedJobs.length === 1 ? "" : "s"}` : "Run a search to find jobs outside your recommendations"}
            </p>
            {searchMutation.data && (
              <div className="rounded-full border border-border bg-card/70 px-3 py-1.5 text-[11.5px]">
                {searchMutation.data.matched || 0} cached jobs · scanned once from warehouse ({searchMutation.data.fetchedFromWarehouse || 0} rows)
              </div>
            )}
          </div>

          {searchMutation.isPending ? (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="glass h-40 rounded-3xl animate-pulse" />
              ))}
            </div>
          ) : searchMutation.isError ? (
            <div className="rounded-[28px] border border-warning/40 bg-warning/10 px-4 py-6 text-center text-[13px] text-warning">
              <p>{apiErrorMessage(searchMutation.error, "Search could not complete right now.")}</p>
              <button type="button" onClick={() => searchMutation.mutate()} className="btn-secondary mt-3 !rounded-full !px-4 !py-2 text-[12px]">
                Retry search
              </button>
            </div>
          ) : !searchRan ? (
            <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-border bg-card/60 py-14 text-center">
              <Search size={38} strokeWidth={1.4} className="mb-3 text-muted-foreground/45" />
              <p className="text-sm font-semibold">Search all India tech jobs</p>
              <p className="mt-1 max-w-md text-[12.5px] text-muted-foreground">
                Start with All India for maximum supply, then narrow by city or job type.
              </p>
            </div>
          ) : searchedJobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-[28px] border border-dashed border-border bg-card/60 py-16 text-center">
              <Search size={40} strokeWidth={1} className="mb-3 text-muted-foreground/40" />
              <p className="text-sm font-semibold">No matching search results</p>
              <p className="mt-1 max-w-md text-[12.5px] text-muted-foreground">
                Try a broader role title, Remote India, or a nearby city.
              </p>
            </div>
          ) : (
            <>
              <div className="job-grid">
                {searchedJobs.map((job) => (
                  <JobMatchCard key={job.id ?? job.job_url} job={job} />
                ))}
              </div>
              {searchHasMore && (
                <div className="mt-6 flex justify-center">
                  <button
                    type="button"
                    onClick={loadMoreSearch}
                    disabled={searchMutation.isPending}
                    className="btn-secondary !rounded-full !px-6 !py-2.5 text-[13px]"
                  >
                    {searchMutation.isPending ? "Loading…" : `Load more (${searchedJobs.length} shown)`}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
