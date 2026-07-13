import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { discoveredJobsApi, matchesApi, publicJobsApi } from "../services/api";
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
  return String(value).split(",").map((item) => item.trim()).filter(Boolean);
}

function profileExperience(profile) {
  const months = Number(profile?.experience_months || 0) + Number(profile?.experience_years || 0) * 12;
  if (months <= 12) return "fresher";
  if (months <= 36) return "junior";
  if (months <= 72) return "mid";
  return "senior";
}

function hasRecommendationProfile(profile) {
  return Boolean(
    profile?.resume_text &&
    asList(profile?.desired_roles).length > 0 &&
    asList(profile?.preferred_locations).length > 0
  );
}

function SearchLocationPicker({ value, onChange }) {
  const [needle, setNeedle] = useState("");
  const selected = value.length ? value : ["India"];
  const visible = SEARCH_LOCATION_OPTIONS.filter((item) =>
    item.toLowerCase().includes(needle.trim().toLowerCase())
  );
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
    <div className="rounded-xl border border-border bg-card/80 p-3">
      <div className="flex flex-wrap gap-1.5 mb-2">
        {selected.map((item) => (
          <span key={item} className="pill pill-brand">{item}</span>
        ))}
      </div>
      <label className="flex items-center gap-2 input-glass !py-2 mb-2">
        <Search size={14} className="text-muted-foreground shrink-0" />
        <input
          value={needle}
          onChange={(event) => setNeedle(event.target.value)}
          placeholder="Search India locations..."
          className="flex-1 bg-transparent text-[13px] outline-none text-foreground"
        />
      </label>
      <div className="max-h-44 overflow-y-auto pr-1 space-y-2">
        {remoteVisible.length > 0 && (
          <div>
            <p className="px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">National / Remote</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-1">
              {remoteVisible.map((item) => (
                <label key={item} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] hover:bg-muted cursor-pointer">
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
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-1">
              {cityVisible.map((item) => (
                <label key={item} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12px] hover:bg-muted cursor-pointer">
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
  const profileReady = hasRecommendationProfile(profile);
  const defaultExperience = profileExperience(profile);

  useEffect(() => {
    if (!profile) return;
    if (!experience) setExperience(defaultExperience);
    if (!searchExperience) setSearchExperience(defaultExperience);
    if (searchDefaultsSeededRef.current) return;
    if (desiredRoles.length) setSearchRole(desiredRoles[0]);
    if (locations.length) setSearchLocations(locations.slice(0, 4));
    searchDefaultsSeededRef.current = true;
  }, [defaultExperience, desiredRoles, experience, locations, profile, searchExperience]);

  const completed =
    (profile?.resume_text ? 1 : 0) +
    (desiredRoles.length > 0 ? 1 : 0) +
    (locations.length > 0 ? 1 : 0);

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

  const searchMutation = useMutation({
    mutationFn: async () => {
      const requestedLocations = searchLocations.length ? searchLocations : ["India"];
      const locationsToSearch = requestedLocations.includes("India")
        ? ["India"]
        : requestedLocations.slice(0, 8);
      const responses = await Promise.all(locationsToSearch.map((item) =>
        publicJobsApi.search({
          role: searchRole,
          location: item,
          experience: searchExperience,
          workArrangement: searchWorkMode || undefined,
          postedWithinDays: searchFreshness || 7,
          pages: 8,
        }).then((response) => response.data)
      ));
      const seen = new Set();
      const jobs = [];
      for (const response of responses) {
        for (const job of response.jobs || []) {
          const key = job.job_url || `${job.company}-${job.title}-${job.location}`;
          if (seen.has(key)) continue;
          seen.add(key);
          jobs.push(job);
        }
      }
      return {
        query: searchRole,
        location: locationsToSearch.join(", "),
        jobs,
        fetched: responses.reduce((sum, item) => sum + (item.fetched || 0), 0),
        saved: responses.reduce((sum, item) => sum + (item.saved || 0), 0),
      };
    },
    onSuccess: () => setSearchRan(true),
  });

  const remove = useMutation({
    mutationFn: (job) => discoveredJobsApi.remove(job.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["matches"] }),
  });

  const recommendedJobs = Array.isArray(matchesQuery.data) ? matchesQuery.data : [];
  const visibleRecommended = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return recommendedJobs;
    return recommendedJobs.filter((job) =>
      [job.title, job.company, job.location].some((value) => String(value || "").toLowerCase().includes(needle))
    );
  }, [recommendedJobs, query]);

  const searchedJobs = Array.isArray(searchMutation.data?.jobs) ? searchMutation.data.jobs : [];

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
    if (!searchRole.trim()) return;
    searchMutation.mutate();
  }

  return (
    <main className="px-5 py-6 md:px-8 w-full max-w-7xl mx-auto">
      <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight !not-italic">Jobs</h1>
          <p className="text-[13px] text-muted-foreground mt-1 max-w-2xl">
            Recommendations are profile-based. Search is controlled by your role, experience, location, and job type.
          </p>
        </div>
        <div className="inline-flex w-fit rounded-xl border border-border bg-card p-1 shadow-sm">
          <button type="button" onClick={() => setMode("recommended")} className={`px-3 py-1.5 text-[12px] font-semibold rounded-lg ${mode === "recommended" ? "bg-brand text-white" : "text-muted-foreground"}`}>
            Recommended
          </button>
          <button type="button" onClick={() => setMode("search")} className={`px-3 py-1.5 text-[12px] font-semibold rounded-lg ${mode === "search" ? "bg-brand text-white" : "text-muted-foreground"}`}>
            Search Jobs
          </button>
        </div>
      </header>

      {profileLoading ? (
        <div className="glass-subtle rounded-xl h-16 animate-pulse mb-4" />
      ) : profileError ? (
        <div className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-[13px] text-warning mb-4">
          Sign in again to load recommendations from your profile. Search still works from the Search Jobs tab.
        </div>
      ) : mode === "recommended" ? (
        <ProfileGate completed={completed} required={3} />
      ) : null}

      {mode === "recommended" && !profileLoading && profileReady && (
        <>
          <section className="glass-subtle rounded-2xl p-4 mb-4 space-y-3" aria-label="Recommended job filters">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-[13px] font-semibold text-foreground">Recommended Jobs</h2>
                <p className="text-[12px] text-muted-foreground mt-0.5">
                  Uses your saved resume, desired roles, desired locations, and experience.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => refresh.mutate()} disabled={refresh.isPending} className="btn-secondary !py-2 !px-3 text-[12px]">
                  <RefreshCw size={14} className={refresh.isPending ? "animate-spin" : ""} />
                  {refresh.isPending ? "Refreshing" : "Refresh jobs"}
                </button>
                <button type="button" onClick={resetFilters} className="text-[12px] font-semibold text-brand hover:underline">
                  Clear
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-3">
              <label className="flex items-center gap-2 input-glass !py-2 xl:col-span-2">
                <Search size={14} className="text-muted-foreground shrink-0" />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title or company..." className="flex-1 bg-transparent text-[13px] outline-none text-foreground" />
              </label>
              <input className="input-glass !py-2" value={role} onChange={(event) => setRole(event.target.value)} placeholder="Role filter" />
              <select className="input-glass !py-2" value={experience || defaultExperience} onChange={(event) => setExperience(event.target.value)}>
                {EXPERIENCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <select className="input-glass !py-2" value={location} onChange={(event) => setLocation(event.target.value)}>
                <option value="">All desired locations</option>
                {locations.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select className="input-glass !py-2" value={workMode} onChange={(event) => setWorkMode(event.target.value)}>
                {WORK_MODE_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <label className="inline-flex items-center gap-2 text-[12px] text-muted-foreground">
                <SlidersHorizontal size={14} />
                <select className="input-glass !py-2 !w-full" value={freshness} onChange={(event) => setFreshness(event.target.value)}>
                  {FRESHNESS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
          </section>

          <p className="text-[12px] text-muted-foreground mb-3 tnum">
            {visibleRecommended.length} recommended job{visibleRecommended.length === 1 ? "" : "s"}
            {matchesQuery.isFetching || refresh.isPending ? " - updating" : ""}
          </p>
          {(refresh.isPending || refresh.data) && (
            <div className="mb-3 rounded-xl border border-border bg-muted/30 px-3 py-2 text-[12px] text-muted-foreground">
              {refresh.isPending ? "Refreshing recommendations from your latest profile..." : `Last refresh found ${refresh.data?.returned || visibleRecommended.length || 0} recommendation${(refresh.data?.returned || visibleRecommended.length || 0) === 1 ? "" : "s"}.`}
            </div>
          )}

          {matchesQuery.isLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, index) => <div key={index} className="glass rounded-2xl h-40 animate-pulse" />)}
            </div>
          ) : visibleRecommended.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center rounded-2xl border border-dashed border-border">
              <Search size={40} strokeWidth={1} className="text-muted-foreground/40 mb-3" />
              <p className="text-sm font-semibold">No profile-fit recommendations yet</p>
              <p className="text-[12.5px] text-muted-foreground mt-1 max-w-md">
                We are filtering by desired location and experience. Use Search Jobs for a manual role/location search.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {visibleRecommended.map((job) => (
                <JobMatchCard key={job.id ?? job.job_url} job={job} removing={remove.isPending} onRemove={(item) => remove.mutate(item)} />
              ))}
            </div>
          )}
        </>
      )}

      {mode === "search" && (
        <>
          <form onSubmit={runSearch} className="glass-subtle rounded-2xl p-4 mb-4 space-y-4" aria-label="Manual job search">
            <div>
              <h2 className="text-[13px] font-semibold text-foreground">Search Jobs</h2>
              <p className="text-[12px] text-muted-foreground mt-0.5">
                Search by your own role, experience, location, and job type.
              </p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
              <input className="input-glass !py-2 xl:col-span-2" value={searchRole} onChange={(event) => setSearchRole(event.target.value)} placeholder="Job role, e.g. Software Engineer" />
              <select className="input-glass !py-2" value={searchExperience} onChange={(event) => setSearchExperience(event.target.value)}>
                {EXPERIENCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <select className="input-glass !py-2" value={searchWorkMode} onChange={(event) => setSearchWorkMode(event.target.value)}>
                {WORK_MODE_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <select className="input-glass !py-2" value={searchFreshness} onChange={(event) => setSearchFreshness(event.target.value)}>
                {FRESHNESS.filter((option) => option.value !== "").map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </div>
            <SearchLocationPicker value={searchLocations} onChange={setSearchLocations} />
            <div className="flex items-center justify-between gap-3">
              <p className="text-[12px] text-muted-foreground">
                All India searches nationally. Pick cities only when the user wants a strict city search.
              </p>
              <button type="submit" disabled={searchMutation.isPending || !searchRole.trim()} className="btn-gradient !py-2 !px-4 text-[12px]">
                <Search size={14} />
                {searchMutation.isPending ? "Searching" : "Search jobs"}
              </button>
            </div>
          </form>

          <p className="text-[12px] text-muted-foreground mb-3 tnum">
            {searchRan ? `${searchedJobs.length} search result${searchedJobs.length === 1 ? "" : "s"}` : "Run a search to find jobs outside your recommendations"}
          </p>

          {searchMutation.isPending ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, index) => <div key={index} className="glass rounded-2xl h-40 animate-pulse" />)}
            </div>
          ) : searchMutation.isError ? (
            <div className="rounded-2xl border border-warning/40 bg-warning/10 px-4 py-6 text-center text-[13px] text-warning">
              Search could not complete right now. Try a narrower role or location.
            </div>
          ) : !searchRan ? (
            <div className="flex flex-col items-center justify-center py-14 text-center rounded-2xl border border-dashed border-border bg-card/60">
              <Search size={38} strokeWidth={1.4} className="text-muted-foreground/45 mb-3" />
              <p className="text-sm font-semibold">Search all India tech jobs</p>
              <p className="text-[12.5px] text-muted-foreground mt-1 max-w-md">
                Start with All India for maximum supply, then narrow by city or job type.
              </p>
            </div>
          ) : searchedJobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center rounded-2xl border border-dashed border-border">
              <Search size={40} strokeWidth={1} className="text-muted-foreground/40 mb-3" />
              <p className="text-sm font-semibold">No matching search results</p>
              <p className="text-[12.5px] text-muted-foreground mt-1 max-w-md">
                Try a broader role title, Remote India, or a nearby city.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {searchedJobs.map((job) => <JobMatchCard key={job.id ?? job.job_url} job={job} />)}
            </div>
          )}
        </>
      )}
    </main>
  );
}
