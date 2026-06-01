import { useEffect, useRef, useState } from "react";
import api from "../services/api";

const IS_DEV = import.meta.env.DEV;
const DEFAULT_DAYS = 30;

// ── helpers ─────────────────────────────────────────────────────────────────

function formatFrom(raw) {
  if (!raw) return "Unknown";
  const m = raw.match(/^"?([^"<]+)"?\s*<[^>]+>$/);
  return m ? m[1].trim() : raw.split("@")[0] || raw || "Unknown";
}

function formatTime(raw) {
  try {
    return new Date(raw).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function formatDayMonth(iso) {
  try {
    const d = new Date(iso + "T00:00:00");
    return `${d.getDate()} ${d.toLocaleDateString("en-US", { month: "short" })}`;
  } catch {
    return iso;
  }
}

function formatDayLabel(iso, weekday) {
  try {
    const d = new Date(iso + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    if (d.getTime() === today.getTime()) return "Today";
    if (d.getTime() === yesterday.getTime()) return "Yesterday";
    return `${weekday}, ${formatDayMonth(iso)}`;
  } catch {
    return weekday;
  }
}

function formatSince(iso) {
  try {
    const d = new Date(iso + "T00:00:00");
    return `${d.getDate()} ${d.toLocaleDateString("en-US", { month: "short" })} ${d.getFullYear()}`;
  } catch {
    return iso;
  }
}

// Backend only returns previous_days with count > 0. Interpolate empty days so
// the nav shows the full window — empty days appear as muted "—" rows.
function fillEmptyDays(prev, sinceISO, todayISO) {
  const existing = new Map(prev.map((d) => [d.date, d]));
  const since = new Date(sinceISO + "T00:00:00Z");
  const today = new Date(todayISO + "T00:00:00Z");
  const cursor = new Date(today);
  cursor.setUTCDate(cursor.getUTCDate() - 1);
  const out = [];
  while (cursor.getTime() >= since.getTime()) {
    const iso = cursor.toISOString().slice(0, 10);
    const hit = existing.get(iso);
    out.push(
      hit || {
        date: iso,
        weekday: cursor.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" }),
        count: 0,
        messages: [],
      },
    );
    cursor.setUTCDate(cursor.getUTCDate() - 1);
  }
  return out;
}

const avatarPalette = [
  ["#dbeafe", "#1d4ed8"], ["#f3e8ff", "#7c3aed"], ["#fce7f3", "#be185d"],
  ["#dcfce7", "#15803d"], ["#fff7ed", "#c2410c"], ["#fef9c3", "#a16207"],
];
function avatarColors(name) {
  if (!name) return ["#f1f5f9", "#64748b"];
  return avatarPalette[name.charCodeAt(0) % avatarPalette.length] || ["#f1f5f9", "#64748b"];
}

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return err?.message || fallback;
}

// ── page ────────────────────────────────────────────────────────────────────

export default function Applications() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloading, setReloading] = useState(false);
  const [debugOn, setDebugOn] = useState(false);

  const load = async (debug = false, fresh = false) => {
    try {
      const params = new URLSearchParams({ days: String(DEFAULT_DAYS) });
      if (debug && IS_DEV) params.set("debug", "true");
      if (fresh) params.set("fresh", "true");
      const { data } = await api.get(`/mail-applications/tracker?${params}`);
      setData(data);
      setError(null);
    } catch (e) {
      // 409 "No Gmail account connected" is a guided state, not an error to scream about.
      if (e?.response?.status === 409) {
        setError("Connect your Gmail account first (from email-auto) to see your application count.");
      } else {
        setError(errorMessage(e, "Failed to load applications."));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    void load();
  }, []);

  const handleSync = async () => {
    if (reloading) return;
    setReloading(true);
    try {
      await load(debugOn, /* fresh */ true);
    } finally {
      setReloading(false);
    }
  };

  const toggleDebug = async () => {
    if (!IS_DEV) return;
    const next = !debugOn;
    setDebugOn(next);
    setLoading(true);
    await load(next);
  };

  const flatDays = data
    ? [
        {
          date: data.today.date,
          weekday: new Date(data.today.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short" }),
          count: data.today.count,
          messages: data.today.messages,
          isToday: true,
        },
        ...data.previous_days.map((d) => ({ ...d, isToday: false })),
      ]
    : [];

  const navDays = data ? fillEmptyDays(data.previous_days, data.since_date, data.today.date) : [];

  return (
    <div className="grid gap-6 py-6 max-w-[1280px] mx-auto w-full md:grid-cols-[minmax(240px,22%)_minmax(0,1fr)]">
      {/* LEFT — count panel + day nav */}
      <aside className="flex flex-col gap-5 md:sticky md:top-4 md:self-start md:max-h-[calc(100vh-6rem)] md:overflow-y-auto glass rounded-3xl p-5">
        <section>
          <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.12em] mb-1 flex items-center gap-1.5">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20 7H4a2 2 0 00-2 2v9a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
            Applications
          </p>
          <p className="text-[12px] text-slate-500 mb-3">
            {data ? `Since ${formatSince(data.since_date)}` : "—"}
          </p>
          <div className="flex items-baseline gap-2 flex-wrap mb-1.5">
            <h1 className="text-[48px] sm:text-[58px] tracking-[-1px] leading-[0.95] font-bold text-slate-900">
              {loading ? <span className="inline-block h-12 w-20 bg-slate-200/70 rounded animate-pulse align-bottom" /> : data?.total ?? 0}
            </h1>
            <span className="text-[13px] text-slate-500 font-medium">
              {data?.total === 1 ? "application" : "applications"}
            </span>
          </div>
          <div className="text-[12px] text-slate-500 mb-4">
            {loading ? (
              <span className="inline-block h-3 w-28 bg-slate-200/70 rounded animate-pulse" />
            ) : (
              <>
                <span className="font-semibold text-slate-900">{data?.today.count ?? 0}</span>{" "}
                {(data?.today.count ?? 0) === 1 ? "application" : "applications"} today
                {data ? ` · ${formatDayMonth(data.today.date)}` : ""}
              </>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleSync}
              disabled={reloading}
              className="btn-primary !py-1.5 !px-3 text-[12px] disabled:opacity-60"
            >
              <svg className={`h-3.5 w-3.5 ${reloading ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {reloading ? "Refreshing…" : "Refresh"}
            </button>
            {IS_DEV && (
              <button
                onClick={toggleDebug}
                className={`h-[34px] px-3 rounded-pill text-[11.5px] font-medium border transition-colors ${
                  debugOn ? "bg-accent-100 text-accent-700 border-accent-200" : "bg-transparent text-slate-500 border-slate-200 hover:text-slate-900"
                }`}
                title="Dev-only: pipeline counters"
              >
                {debugOn ? "Debug on" : "Debug"}
              </button>
            )}
          </div>
        </section>

        {/* Day nav */}
        {loading && (
          <section>
            <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.12em] flex items-center gap-1.5 mb-3 px-0.5">Days</p>
            <ul className="space-y-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <li key={i} className="h-6 bg-slate-200/60 rounded animate-pulse" />
              ))}
            </ul>
          </section>
        )}
        {!loading && !error && data && (
          <section>
            <p className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-[0.12em] mb-3 px-0.5">Days</p>
            {navDays.length === 0 ? (
              <p className="text-[11.5px] text-slate-500 px-0.5">
                Past days appear as you keep using the app.
              </p>
            ) : (
              <ul className="space-y-0.5">
                <li>
                  <a
                    href="#day-today"
                    className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-md hover:bg-white/55 transition-colors no-underline"
                  >
                    <span className="text-[12px] font-semibold text-slate-900">Today</span>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10.5px] font-semibold text-slate-900 bg-white/70 border border-slate-200">
                      {data.today.count}
                    </span>
                  </a>
                </li>
                {navDays.map((day) => {
                  const empty = day.count === 0;
                  return (
                    <li key={day.date}>
                      <a
                        href={empty ? undefined : `#day-${day.date}`}
                        className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md transition-colors no-underline ${
                          empty ? "cursor-default" : "hover:bg-white/55"
                        }`}
                      >
                        <span className={`text-[12px] ${empty ? "text-slate-400" : "text-slate-900 font-semibold"}`}>
                          {formatDayLabel(day.date, day.weekday)}
                        </span>
                        {empty ? (
                          <span className="text-[10.5px] text-slate-400">—</span>
                        ) : (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10.5px] font-semibold text-slate-900 bg-white/70 border border-slate-200">
                            {day.count}
                          </span>
                        )}
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}
      </aside>

      {/* RIGHT — inbox-style mail list */}
      <section className="min-w-0">
        {IS_DEV && debugOn && data?.debug && <DebugPanel debug={data.debug} />}

        {loading ? (
          <DayBucketsSkeleton />
        ) : error ? (
          <div className="glass rounded-3xl p-5 flex items-start gap-3">
            <svg className="h-5 w-5 text-rose-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="text-[14px] font-semibold text-rose-700">Could not load applications</p>
              <p className="text-[13px] text-slate-500 mt-0.5">{error}</p>
            </div>
          </div>
        ) : data ? (
          <div className="space-y-5">
            {flatDays.map((day) => (
              <DaySection key={day.date} day={day} />
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function DaySection({ day }) {
  const anchorId = day.isToday ? "day-today" : `day-${day.date}`;
  const label = day.isToday ? "Today" : formatDayLabel(day.date, day.weekday);
  return (
    <div id={anchorId} className="space-y-2 scroll-mt-4">
      <div className="flex items-baseline justify-between px-1">
        <p className="text-[12px] font-semibold text-slate-900">
          {label}
          <span className="ml-2 text-[11px] text-slate-500 font-normal">{formatDayMonth(day.date)}</span>
        </p>
        <p className="text-[11px] text-slate-500">
          {day.count} {day.count === 1 ? "application" : "applications"}
        </p>
      </div>
      {day.count > 0 ? (
        <ul className="glass rounded-3xl divide-y divide-slate-200/70 overflow-hidden">
          {day.messages.map((m) => (
            <MessageRow key={m.id} m={m} />
          ))}
        </ul>
      ) : (
        <div className="glass rounded-3xl py-6 px-5 flex items-center gap-3 text-center justify-center">
          <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M20 7H4a2 2 0 00-2 2v9a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM8 7V5a2 2 0 012-2h4a2 2 0 012 2v2" />
          </svg>
          <p className="text-[13px] text-slate-500">
            {day.isToday ? "No applications today (yet)" : "No applications"}
          </p>
        </div>
      )}
    </div>
  );
}

function MessageRow({ m }) {
  const name = formatFrom(m.from_email);
  const [bg, fg] = avatarColors(name);
  return (
    <li>
      <a
        href={`https://mail.google.com/mail/u/0/#inbox/${m.thread_id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-start gap-3 px-5 py-3 hover:bg-white/55 transition-colors no-underline group"
      >
        <div
          className="h-8 w-8 rounded-full flex items-center justify-center text-[11px] font-bold flex-shrink-0 uppercase"
          style={{ background: bg, color: fg }}
        >
          {name.charAt(0)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2 mb-0.5">
            <span className="text-[13px] font-semibold text-slate-900 truncate">{name}</span>
            <span className="text-[11px] text-slate-500 flex-shrink-0">{formatTime(m.date)}</span>
          </div>
          <p className="text-[12.5px] font-medium text-slate-900 truncate">{m.subject}</p>
          <p className="text-[11.5px] text-slate-500 truncate mt-0.5">{m.snippet}</p>
        </div>
      </a>
    </li>
  );
}

function DayBucketsSkeleton() {
  return (
    <div className="space-y-5">
      {Array.from({ length: 2 }).map((_, di) => (
        <div key={di} className="space-y-2">
          <div className="h-3 w-32 bg-slate-200/60 rounded animate-pulse" />
          <div className="glass rounded-3xl divide-y divide-slate-200/70 overflow-hidden">
            {Array.from({ length: 3 }).map((__, ri) => (
              <div key={ri} className="flex items-start gap-3 px-5 py-3">
                <div className="h-8 w-8 rounded-full bg-slate-200/70 animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-40 bg-slate-200/70 rounded animate-pulse" />
                  <div className="h-3 w-2/3 bg-slate-200/60 rounded animate-pulse" />
                  <div className="h-3 w-1/2 bg-slate-200/50 rounded animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function DebugPanel({ debug }) {
  const rows = [
    { label: "raw_count (Gmail returned)", value: debug.raw_count },
    { label: "in_window_count (inside IST date range)", value: debug.in_window_count },
    { label: "kept_count (counted as applications)", value: debug.kept_count, tone: debug.kept_count > 0 ? "good" : "bad" },
  ];
  const counted = [
    { label: "counted_confident (trusted sender)", value: debug.counted_confident },
    { label: "counted_ai (AI confirmed)", value: debug.counted_ai },
    { label: "counted_context (AI off, job-context)", value: debug.counted_context },
    { label: "ai_reviewed (ambiguous → AI)", value: debug.ai_reviewed },
    { label: "deduped (same-thread collapsed)", value: debug.deduped_count },
  ];
  const breakdownEntries = Object.entries(debug.rejection_breakdown).filter(([, n]) => n > 0);

  return (
    <div className="mb-4 rounded-3xl border-2 border-dashed border-slate-300/60 bg-white/40 p-4 font-mono text-[11.5px] text-slate-700 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold tracking-wider uppercase text-[10px] text-slate-500">Tracker · debug</span>
        <span className="text-slate-500">window: {debug.window.since} → {debug.window.today}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {rows.map((r) => (
          <div key={r.label} className="bg-white/70 rounded-md px-3 py-2 border border-slate-200">
            <p className="text-[10px] uppercase text-slate-500">{r.label}</p>
            <p
              className={`text-[18px] font-bold tabular-nums ${
                r.tone === "good" ? "text-emerald-600" : r.tone === "bad" ? "text-rose-600" : "text-slate-900"
              }`}
            >
              {r.value}
            </p>
          </div>
        ))}
      </div>

      <div>
        <p className="text-[10px] uppercase text-slate-500 mb-1">how counted</p>
        <ul className="space-y-0.5">
          {counted.map(({ label, value }) => (
            <li key={label} className="flex justify-between gap-3">
              <span>{label}</span>
              <span className="font-bold tabular-nums">{value}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="text-[10px] uppercase text-slate-500 mb-1">rejection_breakdown</p>
        {breakdownEntries.length === 0 ? (
          <p className="text-slate-500">— nothing rejected —</p>
        ) : (
          <ul className="space-y-0.5">
            {breakdownEntries.map(([cat, n]) => (
              <li key={cat} className="flex justify-between gap-3">
                <span>{cat}</span>
                <span className="font-bold tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <details className="text-[10.5px]">
        <summary className="cursor-pointer text-slate-500">gmail query (click)</summary>
        <pre className="mt-1 whitespace-pre-wrap break-all bg-white/70 p-2 rounded border border-slate-200">{debug.query}</pre>
      </details>
    </div>
  );
}
