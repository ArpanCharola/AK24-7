import { useState } from "react";
import { Play, Clock, Trash2 } from "lucide-react";
import { jobSearchesApi } from "../../services/api";
import { timeAgo } from "../../lib/format";

function levelBadge(level) {
  if (!level) return null;
  return <span className="pill pill-brand capitalize">{level}</span>;
}

// One saved search profile: summary + Run (kicks discovery) + last-run time.
export default function JobProfileCard({ profile, onRan, onDeleted }) {
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    try {
      await jobSearchesApi.run(profile.id);
      onRan?.();
    } finally {
      setRunning(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete the "${profile.name}" search?`)) return;
    await jobSearchesApi.remove(profile.id);
    onDeleted?.();
  }

  const roles = profile.target_roles || "All roles";
  const locations = profile.locations || "All locations";

  return (
    <div className="glass rounded-2xl p-4 flex flex-col gap-2 min-w-[240px] w-[260px] shrink-0">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13.5px] font-semibold text-foreground truncate">{profile.name}</p>
        {levelBadge(profile.experience_level)}
      </div>
      <p className="text-[12px] text-muted-foreground truncate" title={roles}>{roles}</p>
      <p className="text-[11.5px] text-muted-foreground/80 truncate" title={locations}>{locations}</p>
      <p className="text-[10.5px] text-muted-foreground/70 inline-flex items-center gap-1">
        <Clock size={11} />
        {profile.last_run_at ? `Last run ${timeAgo(profile.last_run_at)}` : "Not run yet"}
      </p>
      <div className="flex items-center gap-2 mt-1">
        <button onClick={run} disabled={running} className="btn-gradient !py-1.5 !px-3 text-[12px] flex-1">
          <Play size={12} /> {running ? "Running…" : "Run"}
        </button>
        <button onClick={remove} className="btn-secondary !py-1.5 !px-2.5 text-[12px]" title="Delete search">
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );
}
