import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, MailCheck, Plus, RefreshCw, Target } from "lucide-react";
import api from "../services/api";
import TrackerRow from "../components/Tracker/TrackerRow";

const COLUMNS = ["#", "Company", "Job Role", "Job Portal", "Location", "Salary", "Job Type", "Resume", "Job Link", "Status", "Notes", "Contacts", ""];
const QKEY = ["saved-applications"];

function StatCard({ label, value, note, icon: Icon }) {
  return (
    <div className="glass-subtle rounded-[24px] px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold text-foreground tnum">{value}</p>
          <p className="mt-1 text-[12px] text-muted-foreground">{note}</p>
        </div>
        <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-brand/10 text-brand">
          <Icon size={18} />
        </span>
      </div>
    </div>
  );
}

export default function Tracker() {
  const qc = useQueryClient();
  const [toast, setToast] = useState(null);
  const autoRan = useRef(false);

  const showToast = (msg, ms = 4000) => {
    setToast(msg);
    setTimeout(() => setToast(null), ms);
  };

  const { data: rows = [], isLoading } = useQuery({
    queryKey: QKEY,
    queryFn: () => api.get("/saved-applications/").then((r) => r.data),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, patch }) => api.patch(`/saved-applications/${id}`, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: QKEY });
      const prev = qc.getQueryData(QKEY);
      qc.setQueryData(QKEY, (cur = []) => cur.map((r) => (r.id === id ? { ...r, ...patch } : r)));
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(QKEY, ctx.prev);
      showToast("Couldn't save that edit.");
    },
    onSettled: () => qc.invalidateQueries({ queryKey: QKEY }),
  });

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/saved-applications/${id}`),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: QKEY });
      const prev = qc.getQueryData(QKEY);
      qc.setQueryData(QKEY, (cur = []) => cur.filter((r) => r.id !== id));
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(QKEY, ctx.prev);
      showToast("Couldn't delete.");
    },
  });

  const createMut = useMutation({
    mutationFn: () =>
      api.post("/saved-applications/", {
        company: "New Company",
        role: "Role",
        applied_at: new Date().toISOString(),
        status: "to apply",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QKEY }),
  });

  const syncMut = useMutation({
    mutationFn: () => api.post("/mail-applications/auto-track").then((r) => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: QKEY });
      if (data?.created > 0) showToast(`Added ${data.created} application${data.created === 1 ? "" : "s"} from Gmail.`);
      else showToast("No new applications found in Gmail.");
    },
    onError: (e) => {
      if (e?.response?.status !== 409) showToast("Gmail sync failed.");
      else showToast("Connect Gmail first (in Email).");
    },
  });

  useEffect(() => {
    if (autoRan.current) return;
    autoRan.current = true;
    syncMut.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stats = useMemo(() => {
    const total = rows.length;
    const applied = rows.filter((row) => row.status && row.status !== "to apply").length;
    const interviews = rows.filter((row) => ["interview", "offer"].includes(row.status)).length;
    const withLinks = rows.filter((row) => row.job_link).length;
    return { total, applied, interviews, withLinks };
  }, [rows]);

  return (
    <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-5 px-5 py-6 md:px-8">
      <section className="rounded-[32px] border border-border/70 bg-[linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--card)/0.96)_58%,hsl(var(--brand)/0.08)_100%)] px-6 py-7 shadow-[0_24px_70px_-42px_hsl(var(--brand)/0.32)] md:px-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <span className="editorial-kicker">Application command center</span>
            <h1 className="mt-3 text-[clamp(2rem,4vw,3.5rem)] font-semibold leading-[1.02] tracking-tight text-foreground">
              Track every role like a pipeline, not a spreadsheet chore.
            </h1>
            <p className="mt-3 text-[14px] leading-7 text-muted-foreground">
              Capture manual entries, sync application signals from Gmail, and keep interviews, notes, and recruiter contacts in one clean board.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {toast && <span className="rounded-full border border-border bg-card/70 px-3 py-1.5 text-[11.5px] text-muted-foreground">{toast}</span>}
            <button onClick={() => syncMut.mutate()} disabled={syncMut.isPending} className="btn-secondary !rounded-full !px-3 !py-2 text-[12px]">
              <RefreshCw size={13} className={syncMut.isPending ? "animate-spin" : ""} /> Sync from Gmail
            </button>
            <button onClick={() => createMut.mutate()} className="btn-primary !rounded-full !px-4 !py-2 text-[12px]">
              <Plus size={13} /> Add application
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total applications" value={stats.total} note="Everything in your tracker" icon={BriefcaseBusiness} />
        <StatCard label="Active pipeline" value={stats.applied} note="Moved beyond to-apply" icon={Target} />
        <StatCard label="Interviews + offers" value={stats.interviews} note="High-priority follow-ups" icon={MailCheck} />
        <StatCard label="Roles with links" value={stats.withLinks} note="Ready to revisit fast" icon={RefreshCw} />
      </section>

      <section className="glass-subtle overflow-hidden rounded-[30px] border border-border/80 bg-card/80 shadow-sm">
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="text-[15px] font-semibold text-foreground">Tracker table</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {rows.length} application{rows.length !== 1 ? "s" : ""} · click any cell to edit inline
            </p>
          </div>
          <div className="rounded-full border border-border bg-muted/35 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            spreadsheet feel · cleaner shell
          </div>
        </div>

        <div className="overflow-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="sticky top-0 z-10 border-b border-border bg-card/95 backdrop-blur-sm">
                {COLUMNS.map((h, i) => (
                  <th key={i} className="whitespace-nowrap px-3 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b border-border">
                      {COLUMNS.map((__, j) => (
                        <td key={j} className="px-3 py-3">
                          <div className="h-3 rounded bg-muted animate-pulse" />
                        </td>
                      ))}
                    </tr>
                  ))
                : rows.map((row, i) => (
                    <TrackerRow
                      key={row.id}
                      row={row}
                      index={i}
                      onUpdate={(id, patch) => updateMut.mutate({ id, patch })}
                      onDelete={(id) => deleteMut.mutate(id)}
                    />
                  ))}
            </tbody>
          </table>

          {!isLoading && rows.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-sm font-semibold">No applications tracked yet</p>
              <p className="mt-1 text-[12.5px] text-muted-foreground">
                Click <span className="font-medium">Add application</span> or <span className="font-medium">Sync from Gmail</span> to populate your tracker.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
