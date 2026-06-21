import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, RefreshCw } from "lucide-react";
import api from "../services/api";
import TrackerRow from "../components/Tracker/TrackerRow";

const COLUMNS = ["#", "Company", "Job Role", "Job Portal", "Location", "Salary", "Job Type", "Resume", "Job Link", "Status", "Notes", "Contacts", ""];
const QKEY = ["saved-applications"];

export default function Tracker() {
  const qc = useQueryClient();
  const [toast, setToast] = useState(null);
  const autoRan = useRef(false);

  const showToast = (msg, ms = 4000) => { setToast(msg); setTimeout(() => setToast(null), ms); };

  const { data: rows = [], isLoading } = useQuery({
    queryKey: QKEY,
    queryFn: () => api.get("/saved-applications/").then((r) => r.data),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, patch }) => api.patch(`/saved-applications/${id}`, patch),
    // Optimistic: reflect the edit immediately, roll back on error.
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: QKEY });
      const prev = qc.getQueryData(QKEY);
      qc.setQueryData(QKEY, (cur = []) => cur.map((r) => (r.id === id ? { ...r, ...patch } : r)));
      return { prev };
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) qc.setQueryData(QKEY, ctx.prev); showToast("Couldn't save that edit."); },
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
    onError: (_e, _v, ctx) => { if (ctx?.prev) qc.setQueryData(QKEY, ctx.prev); showToast("Couldn't delete."); },
  });

  const createMut = useMutation({
    mutationFn: () => api.post("/saved-applications/", {
      company: "New Company", role: "Role", applied_at: new Date().toISOString(), status: "to apply",
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
    onError: (e) => { if (e?.response?.status !== 409) showToast("Gmail sync failed."); else showToast("Connect Gmail first (in Email)."); },
  });

  // Auto-sync once on mount (quietly ignores 'no Gmail connected').
  useEffect(() => {
    if (autoRan.current) return;
    autoRan.current = true;
    syncMut.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-border shrink-0">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Job Tracker</h1>
          <p className="text-[12px] text-muted-foreground">
            {rows.length} application{rows.length !== 1 ? "s" : ""} · click any cell to edit
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {toast && <span className="text-[11.5px] text-muted-foreground hidden md:inline">{toast}</span>}
          <button onClick={() => syncMut.mutate()} disabled={syncMut.isPending} className="btn-secondary !py-1.5 !px-3 text-[12px]">
            <RefreshCw size={13} className={syncMut.isPending ? "animate-spin" : ""} /> Sync from Gmail
          </button>
          <button onClick={() => createMut.mutate()} className="btn-primary !py-1.5 !px-3 text-[12px]">
            <Plus size={13} /> Add
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-border bg-muted/50 sticky top-0 z-10 backdrop-blur-sm">
              {COLUMNS.map((h, i) => (
                <th key={i} className="px-3 py-2.5 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-b border-border">
                    {COLUMNS.map((__, j) => (
                      <td key={j} className="px-3 py-3"><div className="h-3 bg-muted animate-pulse rounded" /></td>
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
            <p className="text-[12.5px] text-muted-foreground mt-1">
              Click <span className="font-medium">+ Add</span> or <span className="font-medium">Sync from Gmail</span> to populate your tracker.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
