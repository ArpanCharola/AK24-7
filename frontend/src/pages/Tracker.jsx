import { useEffect, useRef, useState } from "react";
import api from "../services/api";

const STATUSES = [
  { value: "applied", label: "Applied", badge: "bg-slate-100 text-slate-700" },
  { value: "assessment", label: "Assessment", badge: "bg-violet-100 text-violet-700" },
  { value: "interview", label: "Interview", badge: "bg-sky-100 text-sky-700" },
];

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return err?.message || fallback;
}

function fmtDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

export default function Tracker() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [autoTrackInfo, setAutoTrackInfo] = useState(null);
  const [openCreate, setOpenCreate] = useState(false);
  const [editing, setEditing] = useState(null); // row or null
  const autoTrackedRef = useRef(false);

  const showToast = (msg, ms = 3500) => {
    setToast(msg);
    setTimeout(() => setToast(null), ms);
  };

  const refresh = async () => {
    try {
      const { data } = await api.get("/saved-applications/");
      setItems(data);
      setError(null);
    } catch (e) {
      setError(errorMessage(e, "Failed to load tracker."));
    } finally {
      setLoading(false);
    }
  };

  const runAutoTrack = async () => {
    try {
      const { data } = await api.post("/mail-applications/auto-track");
      if (data.created > 0) {
        showToast(`Auto-added ${data.created} new application${data.created === 1 ? "" : "s"} from Gmail.`, 5000);
        await refresh();
      }
      setAutoTrackInfo(data);
    } catch (e) {
      // Quiet about 409 (no Gmail connected) — user just hasn't connected yet.
      if (e?.response?.status !== 409) {
        // eslint-disable-next-line no-console
        console.warn("auto-track failed:", errorMessage(e, "unknown"));
      }
    }
  };

  useEffect(() => {
    void refresh().then(() => {
      // Trigger auto-track once after the initial list loads.
      if (!autoTrackedRef.current) {
        autoTrackedRef.current = true;
        void runAutoTrack();
      }
    });
  }, []);

  const move = async (row, nextStatus) => {
    if (row.status === nextStatus) return;
    const prevStatus = row.status;
    setItems((cur) => cur.map((r) => (r.id === row.id ? { ...r, status: nextStatus } : r)));
    try {
      await api.patch(`/saved-applications/${row.id}`, { status: nextStatus });
    } catch (e) {
      setItems((cur) => cur.map((r) => (r.id === row.id ? { ...r, status: prevStatus } : r)));
      showToast(errorMessage(e, "Couldn't move the card."), 5000);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete ${row.company} — ${row.role}?`)) return;
    const snapshot = items;
    setItems((cur) => cur.filter((r) => r.id !== row.id));
    try {
      await api.delete(`/saved-applications/${row.id}`);
    } catch (e) {
      setItems(snapshot);
      showToast(errorMessage(e, "Couldn't delete."), 5000);
    }
  };

  const columns = STATUSES.map((s) => ({
    ...s,
    items: items.filter((r) => r.status === s.value),
  }));

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Job Tracker</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">
            Your hand-curated pipeline · auto-populated from detected applications · stage moves are manual
          </p>
        </div>
        <div className="flex items-center gap-2">
          {autoTrackInfo && (
            <span className="text-[11.5px] text-slate-400 hidden md:inline">
              Detected {autoTrackInfo.detected} · added {autoTrackInfo.created} · already tracked {autoTrackInfo.already_tracked}
            </span>
          )}
          <button onClick={() => runAutoTrack()} className="btn-secondary !py-1.5 !px-3 text-[12px]">
            Sync from Gmail
          </button>
          <button onClick={() => setOpenCreate(true)} className="btn-primary !py-1.5 !px-3 text-[12px]">
            + Add
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        {toast && <div className="m-3 px-3 py-2 rounded-xl text-[13px] glass-subtle text-slate-700">{toast}</div>}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
            {STATUSES.map((s) => (
              <div key={s.value} className="space-y-2">
                <div className="h-5 w-24 bg-slate-200/60 rounded animate-pulse" />
                {Array.from({ length: 2 }).map((_, i) => (
                  <div key={i} className="h-24 bg-slate-200/40 rounded-xl animate-pulse" />
                ))}
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="m-4 px-4 py-3 rounded-xl bg-rose-50 text-rose-700 text-[13px]">{error}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4">
            {columns.map((col) => (
              <Column key={col.value} col={col} onMove={move} onEdit={setEditing} onDelete={remove} />
            ))}
          </div>
        )}
      </div>

      {openCreate && (
        <EditModal
          onClose={() => setOpenCreate(false)}
          onSaved={(row) => {
            setItems((cur) => [row, ...cur]);
            setOpenCreate(false);
            showToast("Saved.");
          }}
        />
      )}

      {editing && (
        <EditModal
          row={editing}
          onClose={() => setEditing(null)}
          onSaved={(row) => {
            setItems((cur) => cur.map((r) => (r.id === row.id ? row : r)));
            setEditing(null);
            showToast("Updated.");
          }}
        />
      )}
    </div>
  );
}

function Column({ col, onMove, onEdit, onDelete }) {
  return (
    <div className="glass-subtle rounded-2xl p-3">
      <div className="flex items-center justify-between mb-3 px-1">
        <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${col.badge}`}>{col.label}</span>
        <span className="text-[11px] text-slate-500 font-medium">{col.items.length}</span>
      </div>
      {col.items.length === 0 ? (
        <p className="text-[12px] text-slate-400 text-center py-6">No applications here yet.</p>
      ) : (
        <ul className="space-y-2">
          {col.items.map((row) => (
            <Card key={row.id} row={row} onMove={onMove} onEdit={onEdit} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Card({ row, onMove, onEdit, onDelete }) {
  const otherStatuses = STATUSES.filter((s) => s.value !== row.status);
  return (
    <li className="bg-white/85 rounded-xl px-3 py-2.5 border border-white/60 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-slate-900 truncate">{row.company}</p>
          <p className="text-[12px] text-slate-600 truncate">{row.role}</p>
        </div>
        <button
          onClick={() => onDelete(row)}
          title="Delete"
          className="text-slate-400 hover:text-rose-600 text-[15px] leading-none px-1"
        >
          ×
        </button>
      </div>
      <p className="text-[11px] text-slate-400 mb-2">Applied {fmtDate(row.applied_at)}</p>
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-1">
          {otherStatuses.map((s) => (
            <button
              key={s.value}
              onClick={() => onMove(row, s.value)}
              className="px-1.5 py-0.5 rounded-md text-[10.5px] font-medium text-slate-500 hover:text-slate-900 hover:bg-white/80"
              title={`Move to ${s.label}`}
            >
              → {s.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => onEdit(row)}
          className="text-[10.5px] text-slate-500 hover:text-slate-900 font-medium"
        >
          Edit
        </button>
      </div>
      {row.mail_url && (
        <a
          href={row.mail_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block mt-1 text-[10.5px] text-accent-600 truncate hover:underline"
        >
          ↗ Open email
        </a>
      )}
    </li>
  );
}

function EditModal({ row, onClose, onSaved }) {
  const isEdit = !!row;
  const [form, setForm] = useState({
    company: row?.company || "",
    role: row?.role || "",
    applied_at: row?.applied_at ? row.applied_at.slice(0, 10) : new Date().toISOString().slice(0, 10),
    status: row?.status || "applied",
    mail_url: row?.mail_url || "",
    notes: row?.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      const payload = {
        ...form,
        applied_at: new Date(form.applied_at + "T00:00:00").toISOString(),
        mail_url: form.mail_url || null,
        notes: form.notes || null,
      };
      const resp = isEdit
        ? await api.patch(`/saved-applications/${row.id}`, payload)
        : await api.post(`/saved-applications/`, payload);
      onSaved(resp.data);
    } catch (e) {
      setErr(errorMessage(e, "Couldn't save."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg glass-strong rounded-2xl p-5 space-y-3"
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-900">{isEdit ? "Edit application" : "Add application"}</h3>
          <button type="button" onClick={onClose} className="text-slate-400 text-[18px] leading-none">×</button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
            Company
            <input
              required
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
              className="input-glass text-sm mt-1 font-normal normal-case"
              placeholder="Acme Corp"
            />
          </label>
          <label className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
            Role
            <input
              required
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="input-glass text-sm mt-1 font-normal normal-case"
              placeholder="Backend Engineer"
            />
          </label>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
            Applied
            <input
              type="date"
              required
              value={form.applied_at}
              onChange={(e) => setForm({ ...form, applied_at: e.target.value })}
              className="input-glass text-sm mt-1 font-normal normal-case"
            />
          </label>
          <label className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
            Stage
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="input-glass text-sm mt-1 font-normal normal-case"
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
          Email link (optional)
          <input
            value={form.mail_url}
            onChange={(e) => setForm({ ...form, mail_url: e.target.value })}
            className="input-glass text-sm mt-1 font-normal normal-case"
            placeholder="https://mail.google.com/..."
          />
        </label>
        <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
          Notes (optional)
          <textarea
            rows={3}
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            className="input-glass text-sm mt-1 font-normal normal-case resize-none"
            placeholder="Referred by Alex on the platform team."
          />
        </label>
        {err && <p className="text-[12.5px] text-rose-700 bg-rose-50/70 rounded-lg px-3 py-2">{err}</p>}
        <div className="flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="text-[13px] text-slate-500 px-3">Cancel</button>
          <button type="submit" disabled={saving} className="btn-primary !py-1.5 !px-4 text-[13px]">
            {saving ? "Saving…" : isEdit ? "Update" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
