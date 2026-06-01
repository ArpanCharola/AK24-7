import { useEffect, useMemo, useRef, useState } from "react";
import api from "../services/api";

/* TrackerList — a flat list view over the same saved_applications data that
 * powers the /tracker kanban (Tracker.jsx). The two are siblings; this one is
 * search/filter/table oriented. Ported from the Next.js tracker page, mapped
 * onto aiapply's glass + slate design tokens and inline SVG icons. */

/* ---------- tiny className helper ---------- */
const cn = (...a) => a.filter(Boolean).join(" ");

/* ---------- Status config ---------- */

const STATUS_ORDER = ["applied", "assessment", "interview"];

const STATUS_META = {
  applied: { label: "Applied", bg: "rgba(100,116,139,0.14)", color: "#64748b" },
  assessment: { label: "Assessment", bg: "rgba(73,134,231,0.14)", color: "#4986e7" },
  interview: { label: "Interview", bg: "rgba(22,167,102,0.14)", color: "#16a766" },
};

/* Defensive fallback so a legacy row with a since-removed status still renders
 * instead of crashing the page. */
const FALLBACK_STATUS_META = { label: "Applied", bg: "rgba(100,116,139,0.14)", color: "#64748b" };

/* ---------- Inline SVG icons (no lucide-react) ---------- */

const Svg = ({ children, className }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

const IconClipboard = (p) => (
  <Svg {...p}>
    <rect x="8" y="2" width="8" height="4" rx="1" />
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <path d="M12 11h4M12 16h4M8 11h.01M8 16h.01" />
  </Svg>
);
const IconSearch = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </Svg>
);
const IconPencil = (p) => (
  <Svg {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </Svg>
);
const IconTrash = (p) => (
  <Svg {...p}>
    <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
    <path d="M10 11v6M14 11v6" />
  </Svg>
);
const IconExternal = (p) => (
  <Svg {...p}>
    <path d="M15 3h6v6" />
    <path d="M10 14 21 3" />
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
  </Svg>
);
const IconAlert = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="10" />
    <path d="M12 8v4M12 16h.01" />
  </Svg>
);
const IconX = (p) => (
  <Svg {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);
const IconLoader = (p) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </Svg>
);
const IconBuilding = (p) => (
  <Svg {...p}>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M9 22v-4h6v4M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01" />
  </Svg>
);
const IconBriefcase = (p) => (
  <Svg {...p}>
    <rect x="2" y="7" width="20" height="14" rx="2" />
    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
  </Svg>
);

/* ---------- Date helpers ---------- */

/* Date -> "YYYY-MM-DDTHH:mm" in local wall-clock time, for <input datetime-local>. */
function toLocalInputValue(d) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

function nowInputValue() {
  return toLocalInputValue(new Date());
}

/* ISO (or any parseable) -> datetime-local value for editing. */
function isoToInputValue(iso) {
  try {
    return toLocalInputValue(new Date(iso));
  } catch {
    return nowInputValue();
  }
}

/* "28 May 2026 · 10:30 AM" */
function formatApplied(iso) {
  try {
    const d = new Date(iso);
    const date = `${d.getDate()} ${d.toLocaleDateString("en-US", {
      month: "short",
    })} ${d.getFullYear()}`;
    const time = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    return `${date} · ${time}`;
  } catch {
    return iso;
  }
}

const avatarPalette = [
  ["#dbeafe", "#1d4ed8"], ["#f3e8ff", "#7c3aed"], ["#fce7f3", "#be185d"],
  ["#dcfce7", "#15803d"], ["#fff7ed", "#c2410c"], ["#fef9c3", "#a16207"],
];
function companyColors(name) {
  if (!name) return ["#f1f5f9", "#64748b"];
  return avatarPalette[name.charCodeAt(0) % avatarPalette.length] ?? ["#f1f5f9", "#64748b"];
}

function sortApps(list) {
  return [...list].sort((a, b) => {
    const t = new Date(b.applied_at).getTime() - new Date(a.applied_at).getTime();
    if (t !== 0) return t;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
}

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return err?.message || fallback;
}

/* ---------- Form model ---------- */

function emptyForm() {
  return {
    company: "",
    role: "",
    appliedAt: nowInputValue(),
    status: "applied",
    mailUrl: "",
    notes: "",
  };
}

function formFrom(app) {
  return {
    company: app.company,
    role: app.role,
    appliedAt: isoToInputValue(app.applied_at),
    status: app.status,
    mailUrl: app.mail_url ?? "",
    notes: app.notes ?? "",
  };
}

/* ---------- Page ---------- */

export default function TrackerList() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Form modal: holds the application being edited, or null for "create".
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  // Delete confirmation target.
  const [deleteTarget, setDeleteTarget] = useState(null);

  // True while the background auto-tracker is still working (its first run
  // hasn't settled yet). Consent is already granted by the time this page
  // renders (ConsentGate wraps every route), so we kick auto-track on mount and
  // keep an empty list in a "scanning" state until that settles.
  const [autoTrackBusy, setAutoTrackBusy] = useState(true);
  const ranAutoTrackRef = useRef(false);

  const showToast = (msg, ms = 3500) => {
    setToast(msg);
    setTimeout(() => setToast(null), ms);
  };

  const load = async () => {
    try {
      const { data } = await api.get("/saved-applications/");
      setApps(sortApps(data ?? []));
      setError(null);
    } catch (e) {
      setError(errorMessage(e, "Failed to load your job tracker."));
    } finally {
      setLoading(false);
    }
  };

  const runAutoTrack = async () => {
    try {
      const { data } = await api.post("/mail-applications/auto-track");
      if (data?.created > 0) {
        await load();
        showToast(
          `Auto-added ${data.created} new application${data.created === 1 ? "" : "s"} from Gmail.`,
          5000,
        );
      }
    } catch (e) {
      // Quiet about 409 (no Gmail connected) — the user just hasn't linked yet.
      if (e?.response?.status !== 409) {
        // eslint-disable-next-line no-console
        console.warn("auto-track failed:", errorMessage(e, "unknown"));
      }
    } finally {
      setAutoTrackBusy(false);
    }
  };

  useEffect(() => {
    void load().then(() => {
      if (!ranAutoTrackRef.current) {
        ranAutoTrackRef.current = true;
        void runAutoTrack();
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- Derived ---------- */

  const counts = useMemo(() => {
    const byStatus = {};
    const companySet = new Set();
    for (const a of apps) {
      byStatus[a.status] = (byStatus[a.status] ?? 0) + 1;
      companySet.add(a.company.trim().toLowerCase());
    }
    return {
      total: apps.length,
      companies: companySet.size,
      interviewing: (byStatus.assessment ?? 0) + (byStatus.interview ?? 0),
      byStatus,
    };
  }, [apps]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return apps.filter((a) => {
      if (statusFilter !== "all" && a.status !== statusFilter) return false;
      if (!q) return true;
      return (
        a.company.toLowerCase().includes(q) ||
        a.role.toLowerCase().includes(q) ||
        (a.notes ?? "").toLowerCase().includes(q)
      );
    });
  }, [apps, search, statusFilter]);

  /* ---------- Mutations ---------- */

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (app) => {
    setEditing(app);
    setFormOpen(true);
  };

  const handleSaved = (saved) => {
    setApps((prev) => {
      const exists = prev.some((a) => a.id === saved.id);
      const next = exists ? prev.map((a) => (a.id === saved.id ? saved : a)) : [saved, ...prev];
      return sortApps(next);
    });
    showToast(editing ? "Application updated." : `Saved ${saved.company}.`);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    const snapshot = apps;
    setApps((prev) => prev.filter((a) => a.id !== target.id));
    try {
      await api.delete(`/saved-applications/${target.id}`);
      showToast(`Removed ${target.company}.`);
    } catch (e) {
      setApps(snapshot);
      showToast(errorMessage(e, "Could not delete — try again."), 5000);
    }
  };

  /* ---------- Render ---------- */

  return (
    <div className="flex flex-col gap-5 py-5 max-w-[1180px] mx-auto w-full animate-fade-in">
      {toast && (
        <div className="m-0 px-3 py-2 rounded-xl text-[13px] glass-subtle text-slate-700">{toast}</div>
      )}

      {/* HERO */}
      <div className="flex items-start justify-between gap-4 shrink-0">
        <div>
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.12em] mb-1 flex items-center gap-1.5">
            <IconClipboard className="h-3 w-3" />
            Job Tracker
          </p>
          <h1 className="text-[24px] sm:text-[30px] font-semibold tracking-[-0.5px] text-slate-900 leading-tight">
            Every company you've <span className="text-accent-600">applied to.</span>
          </h1>
          <p className="text-[13px] text-slate-500 mt-1">
            Automatically gathered from your inbox — updates here as new applications arrive.
          </p>
        </div>
        <button onClick={openCreate} className="btn-primary !py-1.5 !px-3 text-[12px] shrink-0">
          + Add
        </button>
      </div>

      {/* STAT TILES */}
      <div className="grid grid-cols-3 gap-3 shrink-0">
        <StatTile label="Applications" value={counts.total} loading={loading} />
        <StatTile label="Companies" value={counts.companies} loading={loading} />
        <StatTile label="Interviewing" value={counts.interviewing} loading={loading} accent="#16a766" />
      </div>

      {/* TOOLBAR */}
      <div className="flex flex-col md:flex-row md:items-center gap-3 shrink-0">
        <div className="relative md:w-[300px]">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search company, role, or notes"
            className="w-full h-[36px] pl-9 pr-3 text-[13px] rounded-full bg-white/55 border border-slate-200 focus:border-slate-900/30 outline-none text-slate-900 placeholder:text-slate-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <FilterPill
            active={statusFilter === "all"}
            onClick={() => setStatusFilter("all")}
            label="All"
            count={counts.total}
          />
          {STATUS_ORDER.map((s) => (
            <FilterPill
              key={s}
              active={statusFilter === s}
              onClick={() => setStatusFilter(s)}
              label={STATUS_META[s].label}
              count={counts.byStatus[s] ?? 0}
              dot={STATUS_META[s].color}
            />
          ))}
        </div>
      </div>

      {/* LIST */}
      <div className="min-w-0">
        {loading ? (
          <div className="glass rounded-2xl p-5">
            <SkeletonRows rows={5} />
          </div>
        ) : error ? (
          <div className="glass rounded-2xl p-5 flex items-start gap-3">
            <IconAlert className="h-5 w-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-[14px] font-semibold text-rose-600">Could not load your tracker</p>
              <p className="text-[13px] text-slate-500 mt-0.5">{error}</p>
            </div>
          </div>
        ) : apps.length === 0 ? (
          autoTrackBusy ? <ScanningState /> : <EmptyState />
        ) : filtered.length === 0 ? (
          <div className="glass rounded-2xl py-12 px-6 text-center">
            <IconSearch className="h-6 w-6 text-slate-500 mx-auto opacity-40 mb-2" />
            <p className="text-[13px] text-slate-500">No applications match your filters.</p>
          </div>
        ) : (
          <div className="glass rounded-2xl overflow-hidden">
            {/* Column header — desktop only */}
            <div className="hidden md:grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_140px_120px_72px] gap-3 px-5 py-2.5 border-b border-slate-200 bg-white/40">
              {["Company & role", "Applied", "Status", "Link", ""].map((h, i) => (
                <span
                  key={i}
                  className={cn(
                    "text-[10.5px] font-semibold uppercase tracking-[0.1em] text-slate-500",
                    i === 4 && "text-right",
                  )}
                >
                  {h}
                </span>
              ))}
            </div>

            <ul className="divide-y divide-slate-200">
              {filtered.map((app) => (
                <ApplicationRow
                  key={app.id}
                  app={app}
                  onEdit={() => openEdit(app)}
                  onDelete={() => setDeleteTarget(app)}
                />
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* MODALS */}
      {formOpen && (
        <ApplicationForm
          editing={editing}
          onClose={() => setFormOpen(false)}
          onSaved={handleSaved}
        />
      )}
      {deleteTarget && (
        <DeleteConfirm
          app={deleteTarget}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  );
}

/* ---------- Subcomponents ---------- */

function StatTile({ label, value, loading, accent }) {
  return (
    <div className="glass rounded-2xl px-4 py-3.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-slate-500">{label}</p>
      {loading ? (
        <div className="h-7 w-10 mt-1.5 rounded-md bg-slate-200/60 animate-pulse" />
      ) : (
        <p
          className={cn(
            "text-[28px] font-semibold tracking-[-1px] tabular-nums mt-0.5",
            !accent && "text-slate-900",
          )}
          style={accent ? { color: accent } : undefined}
        >
          {value}
        </p>
      )}
    </div>
  );
}

function FilterPill({ active, onClick, label, count, dot }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 h-[30px] px-3 rounded-full text-[12px] font-medium border transition-colors outline-none",
        active
          ? "bg-accent-500 text-white border-transparent"
          : "bg-transparent text-slate-500 border-slate-200 hover:text-slate-900",
      )}
    >
      {dot && (
        <span
          className="h-1.5 w-1.5 rounded-full inline-block flex-shrink-0"
          style={{ background: active ? "currentColor" : dot }}
          aria-hidden
        />
      )}
      {label}
      <span className={cn("tabular-nums text-[11px]", active ? "text-white/70" : "text-slate-500/70")}>
        {count}
      </span>
    </button>
  );
}

function StatusBadge({ status }) {
  const meta = STATUS_META[status] ?? FALLBACK_STATUS_META;
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wider w-fit"
      style={{ background: meta.bg, color: meta.color }}
    >
      <span className="h-1.5 w-1.5 rounded-full inline-block" style={{ background: meta.color }} />
      {meta.label}
    </span>
  );
}

function ApplicationRow({ app, onEdit, onDelete }) {
  const [bg, fg] = companyColors(app.company);
  return (
    <li className="md:grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_140px_120px_72px] md:items-center gap-3 px-5 py-3.5 hover:bg-white/50 transition-colors flex flex-col items-start">
      {/* Company & role */}
      <div className="flex items-center gap-3 min-w-0 w-full">
        <div
          className="h-9 w-9 rounded-[10px] flex items-center justify-center text-[12px] font-bold flex-shrink-0 uppercase"
          style={{ background: bg, color: fg }}
        >
          {app.company.charAt(0) || "?"}
        </div>
        <div className="min-w-0">
          <p className="text-[13.5px] font-semibold text-slate-900 truncate">{app.company}</p>
          <p className="text-[12px] text-slate-500 truncate">{app.role}</p>
        </div>
      </div>

      {/* Applied */}
      <p className="text-[12px] text-slate-500 md:text-slate-900/80 tabular-nums">
        <span className="md:hidden text-slate-500">Applied · </span>
        {formatApplied(app.applied_at)}
      </p>

      {/* Status */}
      <div>
        <StatusBadge status={app.status} />
      </div>

      {/* Link */}
      <div>
        {app.mail_url ? (
          <a
            href={app.mail_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[12px] font-medium text-accent-600 hover:underline no-underline"
          >
            <IconExternal className="h-3.5 w-3.5" />
            Open
          </a>
        ) : (
          <span className="text-[12px] text-slate-500/60">—</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 md:justify-end w-full md:w-auto">
        <button
          onClick={onEdit}
          aria-label={`Edit ${app.company}`}
          className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-white/70 transition-colors outline-none"
        >
          <IconPencil className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={onDelete}
          aria-label={`Delete ${app.company}`}
          className="p-1.5 rounded-md text-slate-500 hover:text-rose-600 hover:bg-rose-600/10 transition-colors outline-none"
        >
          <IconTrash className="h-3.5 w-3.5" />
        </button>
      </div>
    </li>
  );
}

function SkeletonRows({ rows = 3 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-[10px] bg-slate-200/60 animate-pulse flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3.5 w-40 bg-slate-200/60 rounded animate-pulse" />
            <div className="h-3 w-24 bg-slate-200/40 rounded animate-pulse" />
          </div>
          <div className="h-5 w-20 bg-slate-200/40 rounded-full animate-pulse" />
        </div>
      ))}
    </div>
  );
}

/* Shown when the list is empty but the background auto-tracker is still
 * working — so the page reads as "looking" rather than "nothing here". */
function ScanningState() {
  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-center gap-2.5 mb-4">
        <IconLoader className="h-4 w-4 text-accent-600 animate-spin flex-shrink-0" />
        <div>
          <p className="text-[13.5px] font-semibold text-slate-900">Checking your inbox for applications…</p>
          <p className="text-[12px] text-slate-500">
            This can take a moment the first time — new ones appear here automatically.
          </p>
        </div>
      </div>
      <SkeletonRows rows={3} />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass rounded-2xl py-14 px-6 flex flex-col items-center text-center gap-3">
      <div
        className="h-12 w-12 rounded-[14px] flex items-center justify-center text-white"
        style={{ background: "linear-gradient(135deg,#f31a7c 0%,#ff7a4d 100%)" }}
      >
        <IconBriefcase className="h-5 w-5" />
      </div>
      <div>
        <p className="text-[15px] font-semibold text-slate-900">No applications yet</p>
        <p className="text-[13px] text-slate-500 mt-1 max-w-[360px]">
          As you apply to jobs, the ones we spot in your inbox will show up here automatically.
        </p>
      </div>
    </div>
  );
}

/* ---------- Modal shell ---------- */

function ModalShell({ children, onClose, labelledBy }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Lock background scroll while the modal is open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
    >
      <div className="absolute inset-0 bg-black/45 backdrop-blur-xs" onClick={onClose} aria-hidden />
      <div className="relative glass-strong rounded-2xl w-full max-w-[480px] max-h-[90vh] overflow-y-auto">
        {children}
      </div>
    </div>
  );
}

/* ---------- Form modal ---------- */

const inputCls =
  "w-full h-[38px] px-3 text-[13px] rounded-md bg-white/55 border border-slate-200 focus:border-slate-900/40 outline-none text-slate-900 placeholder:text-slate-500";
const fieldLabelCls = "block text-[12px] font-semibold text-slate-900 mb-1.5";

function ApplicationForm({ editing, onClose, onSaved }) {
  const [form, setForm] = useState(() => (editing ? formFrom(editing) : emptyForm()));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const firstFieldRef = useRef(null);

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const canSubmit = form.company.trim() && form.role.trim() && form.appliedAt && !saving;

  const submit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setErr(null);

    // datetime-local is local wall-clock; toISOString() gives the correct UTC instant.
    let appliedISO;
    try {
      appliedISO = new Date(form.appliedAt).toISOString();
    } catch {
      setErr("Please enter a valid date and time.");
      setSaving(false);
      return;
    }

    const body = {
      company: form.company.trim(),
      role: form.role.trim(),
      applied_at: appliedISO,
      status: form.status,
      mail_url: form.mailUrl.trim() || null,
      notes: form.notes.trim() || null,
    };

    try {
      const resp = editing
        ? await api.patch(`/saved-applications/${editing.id}`, body)
        : await api.post("/saved-applications/", body);
      onSaved(resp.data);
      onClose();
    } catch (e2) {
      setErr(errorMessage(e2, "Could not save — try again."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell onClose={onClose} labelledBy="tracker-form-title">
      <form onSubmit={submit}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 sticky top-0 bg-white z-10">
          <h2 id="tracker-form-title" className="text-[15px] font-semibold text-slate-900">
            {editing ? "Edit application" : "Add application"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-white/70 transition-colors outline-none"
          >
            <IconX className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={fieldLabelCls} htmlFor="f-company">
                Company <span className="text-rose-600">*</span>
              </label>
              <div className="relative">
                <IconBuilding className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
                <input
                  id="f-company"
                  ref={firstFieldRef}
                  value={form.company}
                  onChange={(e) => set("company", e.target.value)}
                  placeholder="Acme Corp"
                  className={cn(inputCls, "pl-9")}
                  maxLength={200}
                  required
                />
              </div>
            </div>
            <div>
              <label className={fieldLabelCls} htmlFor="f-role">
                Role <span className="text-rose-600">*</span>
              </label>
              <div className="relative">
                <IconBriefcase className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-500 pointer-events-none" />
                <input
                  id="f-role"
                  value={form.role}
                  onChange={(e) => set("role", e.target.value)}
                  placeholder="Backend Engineer"
                  className={cn(inputCls, "pl-9")}
                  maxLength={200}
                  required
                />
              </div>
            </div>
          </div>

          <div>
            <label className={fieldLabelCls} htmlFor="f-applied">
              Applied on <span className="text-rose-600">*</span>
            </label>
            <input
              id="f-applied"
              type="datetime-local"
              value={form.appliedAt}
              onChange={(e) => set("appliedAt", e.target.value)}
              className={inputCls}
              required
            />
          </div>

          <div>
            <span className={fieldLabelCls}>Status</span>
            <div className="flex flex-wrap gap-1.5">
              {STATUS_ORDER.map((s) => {
                const active = form.status === s;
                const meta = STATUS_META[s];
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => set("status", s)}
                    className={cn(
                      "inline-flex items-center gap-1.5 h-[30px] px-3 rounded-full text-[12px] font-medium border transition-colors outline-none",
                      active ? "border-transparent" : "border-slate-200 text-slate-500 hover:text-slate-900",
                    )}
                    style={active ? { background: meta.bg, color: meta.color } : undefined}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full inline-block"
                      style={{ background: meta.color }}
                    />
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className={fieldLabelCls} htmlFor="f-url">
              Email / posting link <span className="text-slate-500 font-normal">(optional)</span>
            </label>
            <input
              id="f-url"
              type="url"
              value={form.mailUrl}
              onChange={(e) => set("mailUrl", e.target.value)}
              placeholder="https://mail.google.com/…"
              className={inputCls}
              maxLength={2000}
            />
          </div>

          <div>
            <label className={fieldLabelCls} htmlFor="f-notes">
              Notes <span className="text-slate-500 font-normal">(optional)</span>
            </label>
            <textarea
              id="f-notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Referral, recruiter name, next steps…"
              rows={3}
              maxLength={4000}
              className="w-full px-3 py-2 text-[13px] rounded-md bg-white/55 border border-slate-200 focus:border-slate-900/40 outline-none text-slate-900 placeholder:text-slate-500 resize-none"
            />
          </div>

          {err && (
            <p className="text-[12.5px] text-rose-700 bg-rose-50/70 rounded-lg px-3 py-2">{err}</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-slate-200 sticky bottom-0 bg-white">
          <button
            type="button"
            onClick={onClose}
            className="h-[36px] px-4 rounded-full text-[13px] font-medium text-slate-500 border border-slate-200 hover:text-slate-900 transition-colors outline-none"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="btn-primary flex items-center gap-2 h-[36px] px-4 rounded-full text-[13px] font-medium disabled:opacity-50 outline-none"
          >
            {saving && <IconLoader className="h-3.5 w-3.5 animate-spin" />}
            {editing ? "Save changes" : "Save application"}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

/* ---------- Delete confirm ---------- */

function DeleteConfirm({ app, onCancel, onConfirm }) {
  return (
    <ModalShell onClose={onCancel} labelledBy="tracker-delete-title">
      <div className="p-6">
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 rounded-full bg-rose-600/10 flex items-center justify-center flex-shrink-0">
            <IconTrash className="h-4 w-4 text-rose-600" />
          </div>
          <div className="min-w-0">
            <h2 id="tracker-delete-title" className="text-[15px] font-semibold text-slate-900">
              Remove this application?
            </h2>
            <p className="text-[13px] text-slate-500 mt-1">
              <span className="font-medium text-slate-900">{app.role}</span> at{" "}
              <span className="font-medium text-slate-900">{app.company}</span> will be removed from your
              tracker. This only deletes your saved record — your Gmail is untouched.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 mt-6">
          <button
            onClick={onCancel}
            className="h-[36px] px-4 rounded-full text-[13px] font-medium text-slate-500 border border-slate-200 hover:text-slate-900 transition-colors outline-none"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="h-[36px] px-4 rounded-full text-[13px] font-medium text-white bg-rose-600 hover:opacity-90 transition-opacity outline-none"
          >
            Remove
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
