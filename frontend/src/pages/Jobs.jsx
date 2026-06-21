import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, Download, Plus, X } from "lucide-react";
import { jobSearchesApi, discoveredJobsApi } from "../services/api";
import { useProfile } from "../hooks/useProfile";
import JobProfileCard from "../components/Jobs/JobProfileCard";
import JobMatchCard from "../components/Jobs/JobMatchCard";
import ProfileGate from "../components/Profile/ProfileGate";

const EXPERIENCE_LEVELS = ["entry", "mid", "senior"];

function NewSearchModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", target_roles: "", locations: "", experience_level: "mid" });
  const [saving, setSaving] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      await jobSearchesApi.create({ ...form, is_active: true });
      onCreated();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={onClose}>
      <form onClick={(e) => e.stopPropagation()} onSubmit={submit} className="glass-strong rounded-2xl p-5 w-full max-w-md space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">New job search</h3>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Name *</label>
          <input autoFocus className="input-glass" value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Full Stack — Bangalore" />
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Target roles</label>
          <input className="input-glass" value={form.target_roles}
                 onChange={(e) => setForm({ ...form, target_roles: e.target.value })} placeholder="Software Engineer, Full Stack Developer" />
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Locations</label>
          <input className="input-glass" value={form.locations}
                 onChange={(e) => setForm({ ...form, locations: e.target.value })} placeholder="Bangalore, Remote" />
        </div>
        <div>
          <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Experience level</label>
          <select className="input-glass capitalize" value={form.experience_level}
                  onChange={(e) => setForm({ ...form, experience_level: e.target.value })}>
            {EXPERIENCE_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn-secondary text-[13px]">Cancel</button>
          <button type="submit" disabled={saving || !form.name.trim()} className="btn-primary text-[13px]">
            {saving ? "Creating…" : "Create & run"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default function Jobs() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [exporting, setExporting] = useState(false);

  const { data: profile } = useProfile();
  const { data: profiles = [] } = useQuery({
    queryKey: ["job-searches"],
    queryFn: () => jobSearchesApi.list().then((r) => r.data),
  });
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["discovered-jobs"],
    queryFn: () => discoveredJobsApi.list().then((r) => r.data),
  });

  // 5-field completion gate (mirrors Profile page).
  const completed =
    (profile?.full_name ? 1 : 0) +
    (profile?.phone ? 1 : 0) +
    (profile?.experience_years != null || profile?.experience_months != null ? 1 : 0) +
    ((profile?.preferred_locations?.length || 0) > 0 ? 1 : 0) +
    (profile?.resume_text ? 1 : 0);

  const filtered = (Array.isArray(jobs) ? jobs : []).filter(
    (j) =>
      !search ||
      j.title?.toLowerCase().includes(search.toLowerCase()) ||
      j.company?.toLowerCase().includes(search.toLowerCase())
  );

  async function exportXlsx() {
    setExporting(true);
    try {
      const res = await discoveredJobsApi.export();
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = "ak247-jobs.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function invalidateAll() {
    qc.invalidateQueries({ queryKey: ["discovered-jobs"] });
    qc.invalidateQueries({ queryKey: ["job-searches"] });
  }

  return (
    <div className="p-6 w-full max-w-6xl mx-auto">
      <div className="flex items-end justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Run a search to discover fresh India roles. Every job you find is kept here.
          </p>
        </div>
      </div>

      <ProfileGate completed={completed} />

      {/* Search profiles */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-[13px] font-semibold text-muted-foreground uppercase tracking-wider">Your searches</h2>
        <button onClick={() => setShowNew(true)} className="btn-secondary !py-1.5 !px-3 text-[12px]">
          <Plus size={13} /> New search
        </button>
      </div>
      {profiles.length === 0 ? (
        <div className="glass-subtle rounded-2xl p-6 text-center mb-6">
          <p className="text-[13px] text-muted-foreground">No searches yet. Create one to start discovering jobs.</p>
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2 mb-6">
          {profiles.map((p) => (
            <JobProfileCard key={p.id} profile={p} onRan={invalidateAll} onDeleted={invalidateAll} />
          ))}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <div className="flex items-center gap-2 flex-1 min-w-[200px] input-glass !py-2">
          <Search size={14} className="text-muted-foreground shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search discovered jobs…"
            className="flex-1 bg-transparent text-[13px] outline-none text-foreground"
          />
        </div>
        <button onClick={exportXlsx} disabled={exporting || filtered.length === 0} className="btn-secondary !py-2 !px-3 text-[12px]">
          <Download size={14} /> {exporting ? "Exporting…" : "Export"}
        </button>
      </div>

      <p className="text-[12px] text-muted-foreground mb-3 tnum">
        {filtered.length} job{filtered.length !== 1 ? "s" : ""} in your history
      </p>

      {/* Jobs grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="glass rounded-2xl h-36 animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Search size={44} strokeWidth={1} className="text-muted-foreground/40 mb-3" />
          <p className="text-sm font-semibold">No jobs found</p>
          <p className="text-[12.5px] text-muted-foreground mt-1">
            Run a search above to discover India roles for your profile.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((job) => (
            <JobMatchCard key={job.id ?? job.job_url} job={job} />
          ))}
        </div>
      )}

      {showNew && (
        <NewSearchModal onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); invalidateAll(); }} />
      )}
    </div>
  );
}
