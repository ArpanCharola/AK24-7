import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "../services/api";

/* ---------- Client-side color map (mirrors backend _COLORS in
   app/services/gmail_labels.py). Keyed by exact label name. ---------- */
const LABEL_COLORS = {
  "AI Apply/Confirmed":  { background: "#16a766", color: "#ffffff" },
  "AI Apply/Assessment": { background: "#ffad47", color: "#ffffff" },
  "AI Apply/Interview":  { background: "#4986e7", color: "#ffffff" },
  "AI Apply/Offer":      { background: "#fad165", color: "#000000" },
  "AI Apply/Rejected":   { background: "#999999", color: "#ffffff" },
};
const DEFAULT_SWATCH = { background: "#e2e8f0", color: "#475569" };

function swatchFor(name) {
  return LABEL_COLORS[name] || DEFAULT_SWATCH;
}

/* ---------- Formatting helpers ---------- */
function formatFrom(raw) {
  if (!raw) return "Unknown";
  const m = raw.match(/^\s*"?([^"<]+?)"?\s*<[^>]+>\s*$/);
  if (m) return m[1].trim();
  return raw.split("@")[0] || raw || "Unknown";
}

function formatDate(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d.getTime())) return "";
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return d.toLocaleDateString("en-US", { weekday: "short" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatRelativeTime(d) {
  if (!d) return "never";
  const then = d instanceof Date ? d : new Date(d);
  if (isNaN(then.getTime())) return "never";
  const diffSec = Math.floor((Date.now() - then.getTime()) / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const AVATAR_PALETTE = [
  ["#dbeafe", "#1d4ed8"], ["#f3e8ff", "#7c3aed"], ["#fce7f3", "#be185d"],
  ["#dcfce7", "#15803d"], ["#fff7ed", "#c2410c"], ["#fef9c3", "#a16207"],
];
function getAvatarColors(name) {
  if (!name) return ["#f1f5f9", "#64748b"];
  return AVATAR_PALETTE[name.charCodeAt(0) % AVATAR_PALETTE.length] || ["#f1f5f9", "#64748b"];
}

/* ---------- Inline icons ---------- */
function RefreshIcon({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M23 4v6h-6M1 20v-6h6" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}
function SparkleIcon({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M12 2l1.9 5.6L19.5 9.5 13.9 11.4 12 17l-1.9-5.6L4.5 9.5l5.6-1.9z" />
    </svg>
  );
}
function SearchIcon({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}
function TagIcon({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  );
}
function InboxIcon({ className = "" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

/* ---------- Page ---------- */
export default function Labels() {
  const [labels, setLabels] = useState([]);
  const [labelsLoading, setLabelsLoading] = useState(true);
  const [labelsError, setLabelsError] = useState(null);

  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messagesError, setMessagesError] = useState(null);

  const [query, setQuery] = useState("");
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState(null);
  // eslint-disable-next-line no-unused-vars
  const [, forceTick] = useState(0); // bump so "X ago" stays fresh

  const selectedRef = useRef(null);
  selectedRef.current = selected;

  /* keep "last synced X ago" live */
  useEffect(() => {
    const t = setInterval(() => forceTick((n) => n + 1), 15000);
    return () => clearInterval(t);
  }, []);

  const loadLabels = useCallback(async (autoSelect = false) => {
    try {
      const { data } = await api.get("/email/labels");
      const list = (data?.labels || []).map((l) => ({
        ...l,
        managed: typeof l.name === "string" && l.name.startsWith("AI Apply/"),
      }));
      setLabels(list);
      setLabelsError(null);
      if (autoSelect && list.length > 0 && !selectedRef.current) {
        const firstManaged = list.find((l) => l.managed);
        setSelected(firstManaged || list[0]);
      }
    } catch (e) {
      setLabelsError(e?.response?.data?.detail || "Failed to load labels.");
    } finally {
      setLabelsLoading(false);
    }
  }, []);

  const loadMessages = useCallback(async (label) => {
    if (!label) return;
    setMessagesLoading(true);
    setMessagesError(null);
    try {
      const { data } = await api.get(
        "/email/labels/" + encodeURIComponent(label.id) + "/messages",
        { params: { limit: 25 } },
      );
      setMessages(Array.isArray(data) ? data : []);
    } catch (e) {
      setMessagesError(e?.response?.data?.detail || "Failed to load messages.");
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/email/status");
      setLastSyncedAt(data?.last_synced_at ? new Date(data.last_synced_at) : null);
    } catch {
      /* status is best-effort; ignore */
    }
  }, []);

  /* on mount */
  useEffect(() => {
    loadLabels(true);
    loadStatus();
  }, [loadLabels, loadStatus]);

  /* on label change */
  useEffect(() => {
    if (selected) loadMessages(selected);
  }, [selected?.id, loadMessages, selected]);

  async function handleSyncNow() {
    if (syncing) return;
    setSyncing(true);
    try {
      const { data } = await api.post("/email/labels/sync");
      const labeled = data?.labeled || 0;
      if (labeled > 0) {
        const breakdown = Object.entries(data?.per_label || {})
          .filter(([, n]) => n > 0)
          .map(([k, n]) => `${k}: ${n}`)
          .join(", ");
        setToast(
          `Labeled ${labeled} new ${labeled === 1 ? "message" : "messages"}` +
            (breakdown ? ` (${breakdown})` : ""),
        );
      } else {
        setToast("Up to date.");
      }
      await Promise.all([loadLabels(), loadStatus()]);
      if (selectedRef.current) await loadMessages(selectedRef.current);
    } catch (e) {
      setToast(e?.response?.data?.detail || "Sync failed — try again in a moment.");
    } finally {
      setSyncing(false);
      setTimeout(() => setToast(null), 6000);
    }
  }

  /* derived: grouped + filtered */
  const { managed, custom, noMatches } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = (l) => !q || l.name.toLowerCase().includes(q);
    const m = labels.filter((l) => l.managed && matches(l));
    // "Custom" = the user's own labels only. Gmail system labels (INBOX, SENT,
    // SPAM, TRASH, CATEGORY_*, etc.) come back as type "system" — drop them so
    // the rail shows things the user actually cares about labelling by.
    const c = labels.filter((l) => !l.managed && l.type === "user" && matches(l));
    return { managed: m, custom: c, noMatches: q.length > 0 && m.length === 0 && c.length === 0 };
  }, [labels, query]);

  return (
    <div className="flex flex-col h-full md:h-[calc(100vh-100px)] md:overflow-hidden py-4 gap-4">
      {/* HERO STRIP */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 shrink-0">
        <div>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full glass-subtle text-[10px] font-semibold uppercase tracking-[0.12em] text-accent-600">
            <SparkleIcon className="h-3 w-3" />
            Auto-labels
          </span>
          <h1 className="text-[24px] sm:text-[28px] font-bold tracking-tight text-slate-900 leading-tight mt-2">
            Your mail, sorted automatically.
          </h1>
          <p className="text-[13px] text-slate-500 mt-1 max-w-xl">
            We watch your inbox and tag{" "}
            <span className="font-semibold" style={{ color: "#ffad47" }}>assessment</span> and{" "}
            <span className="font-semibold" style={{ color: "#4986e7" }}>interview</span> mail as it arrives.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="text-right">
            <p className="text-[10.5px] text-slate-500 uppercase tracking-[0.12em] font-semibold">Last synced</p>
            <p className="text-[13px] text-slate-900 font-semibold">{formatRelativeTime(lastSyncedAt)}</p>
          </div>
          <button
            onClick={handleSyncNow}
            disabled={syncing}
            className="inline-flex items-center gap-2 h-9 px-4 rounded-full bg-accent-500 hover:bg-accent-600 text-white text-[12.5px] font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <RefreshIcon className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </div>

      {toast && (
        <div className="px-3 py-2 rounded-xl glass-subtle text-[13px] text-slate-700 shrink-0">
          {toast}
        </div>
      )}

      {/* TWO-PANE */}
      <div className="flex flex-col md:flex-row gap-4 flex-1 min-h-0">
        {/* LEFT — labels */}
        <aside className="md:w-[280px] md:shrink-0 glass rounded-2xl flex flex-col overflow-hidden min-h-[280px] md:min-h-0">
          <div className="px-3 pt-3 pb-2 border-b border-slate-200 shrink-0">
            <div className="relative">
              <SearchIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search labels"
                className="w-full h-[32px] pl-8 pr-3 text-[12.5px] rounded-md bg-white/55 border border-slate-200 focus:border-accent-500 outline-none text-slate-900 placeholder:text-slate-400"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-3">
            {labelsLoading ? (
              <ul className="space-y-1.5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <li
                    key={i}
                    className="h-8 mx-1 bg-slate-200/60 rounded-md animate-pulse"
                  />
                ))}
              </ul>
            ) : labelsError ? (
              <p className="px-3 py-4 text-[12.5px] text-rose-600">{labelsError}</p>
            ) : labels.length === 0 ? (
              <div className="px-3 py-8 text-center space-y-2">
                <TagIcon className="h-6 w-6 text-slate-300 mx-auto" />
                <p className="text-[13px] text-slate-500">No labels yet. They'll appear as mail arrives.</p>
              </div>
            ) : noMatches ? (
              <p className="px-3 py-6 text-center text-[12.5px] text-slate-500">
                No labels match {query}
              </p>
            ) : (
              <>
                {managed.length > 0 && (
                  <Section title="Auto">
                    {managed.map((label) => (
                      <LabelRow
                        key={label.id}
                        label={label}
                        active={selected?.id === label.id}
                        onClick={() => setSelected(label)}
                      />
                    ))}
                  </Section>
                )}
                {custom.length > 0 && (
                  <Section title="Custom">
                    {custom.map((label) => (
                      <LabelRow
                        key={label.id}
                        label={label}
                        active={selected?.id === label.id}
                        onClick={() => setSelected(label)}
                      />
                    ))}
                  </Section>
                )}
              </>
            )}
          </div>
        </aside>

        {/* RIGHT — messages */}
        <section className="flex-1 glass rounded-2xl flex flex-col overflow-hidden min-h-[420px] md:min-h-0">
          <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-200 shrink-0 gap-3">
            {selected ? (
              <>
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className="h-3 w-3 rounded-[4px] flex-shrink-0"
                    style={{ background: swatchFor(selected.name).background }}
                    aria-hidden="true"
                  />
                  <p className="text-[14px] font-semibold text-slate-900 truncate">{selected.name}</p>
                  {!messagesLoading && !messagesError && (
                    <span className="text-[11.5px] text-slate-500 shrink-0">
                      {messages.length} {messages.length === 1 ? "message" : "messages"}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => loadMessages(selected)}
                  disabled={messagesLoading}
                  className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-white/55 transition-colors disabled:opacity-40"
                  aria-label="Reload messages"
                >
                  <RefreshIcon className={`h-4 w-4 ${messagesLoading ? "animate-spin" : ""}`} />
                </button>
              </>
            ) : (
              <span className="text-[13px] text-slate-500">No label selected</span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {!selected ? (
              <EmptyState
                icon={<TagIcon className="h-9 w-9 text-slate-400" />}
                text="Pick a label on the left"
              />
            ) : messagesLoading ? (
              <ul className="divide-y divide-slate-200/70">
                {Array.from({ length: 7 }).map((_, i) => (
                  <li key={i} className="flex items-start gap-3 px-5 py-3.5">
                    <div className="h-9 w-9 rounded-full bg-slate-200/70 animate-pulse flex-shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 w-40 bg-slate-200/70 rounded animate-pulse" />
                      <div className="h-3 w-2/3 bg-slate-200/60 rounded animate-pulse" />
                      <div className="h-3 w-1/2 bg-slate-200/50 rounded animate-pulse" />
                    </div>
                  </li>
                ))}
              </ul>
            ) : messagesError ? (
              <div className="px-6 py-8">
                <p className="text-[14px] font-semibold text-rose-600">Could not load messages</p>
                <p className="text-[13px] text-slate-500 mt-0.5">{messagesError}</p>
              </div>
            ) : messages.length === 0 ? (
              <EmptyState
                icon={<InboxIcon className="h-9 w-9 text-slate-400" />}
                text="No mail with this label yet."
              />
            ) : (
              <ul className="divide-y divide-slate-200">
                {messages.map((email) => (
                  <MessageRow key={email.id} m={email} />
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ---------- Subcomponents ---------- */
function Section({ title, children }) {
  return (
    <div>
      <p className="px-2 mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function LabelRow({ label, active, onClick }) {
  const swatch = swatchFor(label.name);
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        title={label.name}
        className={`w-full flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 rounded-md text-left transition-colors outline-none border-l-[3px] ${
          active
            ? "bg-white/70 border-l-accent-500"
            : "border-l-transparent hover:bg-white/55"
        }`}
      >
        <span
          className="h-3 w-3 rounded-[4px] flex-shrink-0"
          style={{ background: swatch.background }}
          aria-hidden="true"
        />
        <span className={`text-[12.5px] flex-1 truncate ${active ? "font-semibold text-slate-900" : "text-slate-700"}`}>
          {label.name}
        </span>
        {label.managed && (
          <SparkleIcon className="h-3 w-3 text-accent-500 flex-shrink-0" />
        )}
      </button>
    </li>
  );
}

function MessageRow({ m }) {
  const name = formatFrom(m.from_email);
  const [bg, fg] = getAvatarColors(name);
  const href = m.thread_id
    ? `https://mail.google.com/mail/u/0/#inbox/${m.thread_id}`
    : "#";
  return (
    <li>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-start gap-3 px-5 py-3.5 hover:bg-white/55 transition-colors no-underline"
      >
        <div
          className="h-9 w-9 rounded-full flex items-center justify-center text-[12px] font-bold flex-shrink-0 uppercase"
          style={{ background: bg, color: fg }}
        >
          {name.charAt(0)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <span className="text-[13px] font-semibold text-slate-900 truncate">{name}</span>
            <span className="text-[11px] text-slate-500 flex-shrink-0">{formatDate(m.date)}</span>
          </div>
          <p className="text-[12.5px] font-medium text-slate-900 truncate">{m.subject}</p>
          <p className="text-[11.5px] text-slate-500 truncate mt-0.5">{m.snippet}</p>
        </div>
      </a>
    </li>
  );
}

function EmptyState({ icon, text }) {
  return (
    <div className="h-full min-h-[240px] flex flex-col items-center justify-center gap-2.5 px-6 py-10 text-center">
      {icon}
      <p className="text-[13px] text-slate-500">{text}</p>
    </div>
  );
}
