import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../services/api";

// ── Helpers (pure JS) ────────────────────────────────────────────────────
function formatFrom(raw) {
  if (!raw) return "(unknown)";
  const named = raw.match(/^\s*"?([^"<]+?)"?\s*</);
  if (named && named[1].trim()) return named[1].trim();
  const angle = raw.match(/<([^>]+)>/);
  const addr = (angle ? angle[1] : raw).trim();
  const at = addr.indexOf("@");
  return at > 0 ? addr.slice(0, at) : addr;
}

function formatDate(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d)) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  const weekAgo = new Date(now);
  weekAgo.setDate(now.getDate() - 6);
  if (d >= weekAgo) {
    return d.toLocaleDateString([], { weekday: "short" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

const AVATAR_PALETTE = [
  ["bg-rose-100",    "text-rose-700"],
  ["bg-amber-100",   "text-amber-700"],
  ["bg-emerald-100", "text-emerald-700"],
  ["bg-sky-100",     "text-sky-700"],
  ["bg-violet-100",  "text-violet-700"],
  ["bg-slate-200",   "text-slate-700"],
];

function getAvatarColors(name) {
  const key = name || "?";
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

// ── Inline icons ─────────────────────────────────────────────────────────
function InboxIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 8l2.5-4.5A2 2 0 017.27 2.5h9.46a2 2 0 011.77 1L21 8m-18 0v9a2 2 0 002 2h14a2 2 0 002-2V8m-18 0h5l1.5 3h5L18 8h3" />
    </svg>
  );
}
function ComposeIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M11 5H5a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-6m-1.586-9.586a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.414-8.414z" />
    </svg>
  );
}
function RefreshIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M4 4v5h.582A8 8 0 0119.418 9M20 20v-5h-.581A8 8 0 014.582 15" />
    </svg>
  );
}
function SendIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.4 20.6L21 12 3.4 3.4 3 10l13 2-13 2 .4 6.6z" />
    </svg>
  );
}
function CloseIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
function ExternalIcon({ className = "w-4 h-4" }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M14 5h5v5m0-5L10 14M19 14v5a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h5" />
    </svg>
  );
}

// HTML emails are rendered inside a fully-sandboxed iframe (no scripts, no
// same-origin) so remote markup can't touch the app. Plain-text bodies fall back
// to a pre-wrapped block. Either way the body region scrolls when the mail is tall.
function MailReader({ message, detail, loading, error, onClose }) {
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const name = formatFrom(message.from_email || message.from || "");
  const subject = message.subject || "(no subject)";
  const date = formatDate(message.date || message.internal_date || message.received_at);
  const threadId = message.thread_id || message.threadId || message.id;
  const gmailHref = threadId
    ? `https://mail.google.com/mail/u/0/#inbox/${threadId}`
    : "https://mail.google.com/mail/u/0/#inbox";

  const html = detail?.body_html;
  const text = detail?.body_text || detail?.snippet || message.snippet || "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="glass rounded-2xl w-full max-w-4xl h-[90vh] flex flex-col overflow-hidden shadow-glass-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex-shrink-0 flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-200">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-slate-900 truncate">{subject}</p>
            <p className="text-[12.5px] text-slate-500 truncate mt-0.5">
              {name}
              {date ? ` · ${date}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex-shrink-0 w-8 h-8 -mr-1 -mt-1 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-white/55 transition-colors"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-hidden bg-white/40">
          {loading ? (
            <div className="p-5 space-y-2.5 animate-pulse">
              <div className="h-3 w-3/4 rounded bg-slate-200/50" />
              <div className="h-3 w-full rounded bg-slate-200/50" />
              <div className="h-3 w-5/6 rounded bg-slate-200/50" />
              <div className="h-3 w-2/3 rounded bg-slate-200/50" />
            </div>
          ) : error ? (
            <div className="m-4 px-3.5 py-2.5 rounded-xl bg-rose-50 border border-rose-200 text-[12.5px] text-rose-700">
              {error}
            </div>
          ) : html ? (
            <iframe
              title="Email body"
              sandbox=""
              srcDoc={`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><base target="_blank"><style>html,body{margin:0;padding:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;color:#1e293b;word-wrap:break-word;overflow-wrap:break-word;}img{max-width:100%;height:auto;}a{color:#4f46e5;}table{max-width:100%;}</style></head><body>${html}</body></html>`}
              className="w-full h-full border-0 bg-white"
            />
          ) : (
            <div className="h-full overflow-y-auto px-5 py-4">
              <pre className="whitespace-pre-wrap break-words font-sans text-[13.5px] leading-relaxed text-slate-700">
                {text || "This message has no readable text content."}
              </pre>
            </div>
          )}
        </div>

        <footer className="flex-shrink-0 flex items-center justify-end px-5 py-3 border-t border-slate-200">
          <a
            href={gmailHref}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-accent-600 hover:text-accent-700 hover:bg-white/55 transition-colors"
          >
            <ExternalIcon className="w-3.5 h-3.5" />
            Open in Gmail
          </a>
        </footer>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────
export default function EmailHome() {
  const userName =
    (typeof window !== "undefined" && localStorage.getItem("userName")) || "";
  const firstName = userName ? userName.trim().split(/\s+/)[0] : "";

  // emailsSent: null = loading, "—" = errored, number = ok
  const [emailsSent, setEmailsSent] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [inboxError, setInboxError] = useState(null);

  // Reader card: openMsg is the clicked list row (header data shown instantly),
  // detail is the full body fetched on open.
  const [openMsg, setOpenMsg] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  async function openReader(m) {
    setOpenMsg(m);
    setDetail(null);
    setDetailError(null);
    if (!m.id) {
      setDetailError("This message can't be opened — no message id.");
      return;
    }
    setDetailLoading(true);
    try {
      const res = await api.get(`/email/message/${encodeURIComponent(m.id)}`);
      setDetail(res?.data || null);
    } catch (e) {
      setDetailError(
        e?.response?.data?.detail || e?.message || "Failed to load this message."
      );
    } finally {
      setDetailLoading(false);
    }
  }

  function closeReader() {
    setOpenMsg(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  // Note: these only setState *after* their first await, so they're safe to
  // call from the mount effect without tripping react-hooks/set-state-in-effect.
  // The "reset to loading" resets live in refreshAll (an event handler), where
  // synchronous setState is fine; on first mount the initial state already
  // represents the loading view.
  async function loadStats() {
    try {
      const res = await api.get("/dashboard/stats");
      const v = res?.data?.emailsSent;
      setEmailsSent(typeof v === "number" ? v : 0);
    } catch {
      setEmailsSent("—");
    }
  }

  async function loadInbox(fresh = false) {
    try {
      const params = { limit: 8 };
      if (fresh) params.fresh = true;
      const res = await api.get("/email/inbox", { params });
      const data = res?.data;
      let list = [];
      if (Array.isArray(data)) list = data;
      else if (Array.isArray(data?.messages)) list = data.messages;
      setMessages(list.slice(0, 8));
      setInboxError(null);
    } catch (e) {
      setInboxError(
        e?.response?.data?.detail || e?.message || "Failed to load inbox."
      );
      setMessages([]);
    } finally {
      setInboxLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
    loadInbox(false);
  }, []);

  function refreshAll() {
    setEmailsSent(null);
    setInboxLoading(true);
    setInboxError(null);
    loadStats();
    loadInbox(true);
  }

  return (
    <div className="flex flex-col h-full gap-4 animate-fade-in">
      {/* Hero strip */}
      <section className="flex-shrink-0">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full glass-subtle text-[11px] font-semibold text-slate-600 tracking-wide">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-500" />
          Welcome{firstName ? `, ${firstName}` : ""}
        </span>
        <h1 className="mt-3 text-[28px] sm:text-[32px] font-bold text-slate-900 tracking-tight leading-tight">
          Your emails, automated.
        </h1>
        <p className="mt-1.5 text-[13.5px] text-slate-500 max-w-2xl">
          AI-powered Gmail management — compose, read, and track every conversation in one place.
        </p>
      </section>

      {/* Stat + quick action row */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 flex-shrink-0">
        {/* Emails Sent stat */}
        <div className="glass rounded-2xl p-4 flex flex-col justify-between min-h-[112px]">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.14em]">
              Emails Sent
            </span>
            <span className="text-slate-400">
              <SendIcon className="w-4 h-4" />
            </span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-[30px] font-bold text-slate-900 tabular-nums leading-none">
              {emailsSent === null ? (
                <span className="inline-block h-7 w-12 rounded bg-slate-200/40 animate-pulse" />
              ) : (
                emailsSent
              )}
            </span>
            <span className="text-[11.5px] text-slate-500">total</span>
          </div>
        </div>

        {/* Compose Email (primary) */}
        <Link
          to="/email-auto"
          className="rounded-2xl p-4 bg-accent-500 text-white min-h-[112px] flex flex-col justify-between transition-transform hover:-translate-y-0.5 hover:shadow-glass-lg focus:outline-none focus:ring-2 focus:ring-accent-300"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-white">
              Quick action
            </span>
            <ComposeIcon className="w-4 h-4 text-white" />
          </div>
          <div>
            <p className="text-[17px] font-semibold leading-tight">Compose Email</p>
            <p className="text-[12px] text-white/90 mt-0.5">Draft & send with AI</p>
          </div>
        </Link>

        {/* Inbox (secondary) */}
        <Link
          to="/inbox"
          className="glass-subtle rounded-2xl p-4 min-h-[112px] flex flex-col justify-between transition-transform hover:-translate-y-0.5 hover:shadow-glass-lg focus:outline-none focus:ring-2 focus:ring-accent-300"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-accent-600">
              Quick action
            </span>
            <span className="text-accent-600">
              <InboxIcon className="w-4 h-4" />
            </span>
          </div>
          <div>
            <p className="text-[17px] font-semibold text-slate-900 leading-tight">Inbox</p>
            <p className="text-[12px] text-slate-500 mt-0.5">See every conversation</p>
          </div>
        </Link>
      </section>

      {/* Recent Inbox */}
      <section className="glass rounded-2xl flex-1 min-h-[400px] flex flex-col overflow-hidden">
        <header className="flex-shrink-0 flex items-center justify-between gap-3 px-5 py-3.5 border-b border-slate-200">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-slate-500">
              <InboxIcon className="w-4 h-4" />
            </span>
            <h2 className="text-[14px] font-semibold text-slate-900">Recent Inbox</h2>
            {!inboxLoading && !inboxError && (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-100/80 text-emerald-700 text-[10px] font-bold uppercase tracking-wide">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Live
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              type="button"
              onClick={refreshAll}
              disabled={inboxLoading}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-medium text-slate-600 hover:text-slate-900 hover:bg-white/55 disabled:opacity-50 transition-colors"
            >
              <RefreshIcon className={`w-3.5 h-3.5 ${inboxLoading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <Link
              to="/inbox"
              className="text-[12px] font-semibold text-accent-600 hover:text-accent-700 transition-colors whitespace-nowrap"
            >
              View all →
            </Link>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          {inboxError ? (
            <div className="m-4 px-3.5 py-2.5 rounded-xl bg-rose-50 border border-rose-200 text-[12.5px] text-rose-700">
              {inboxError}
            </div>
          ) : inboxLoading ? (
            <ul className="p-2 space-y-1">
              {Array.from({ length: 6 }).map((_, i) => (
                <li
                  key={i}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-xl animate-pulse"
                >
                  <div className="w-8 h-8 rounded-full bg-slate-200/40 flex-shrink-0" />
                  <div className="flex-1 space-y-1.5">
                    <div className="flex justify-between gap-3">
                      <div className="h-2.5 w-32 rounded bg-slate-200/40" />
                      <div className="h-2.5 w-10 rounded bg-slate-200/40" />
                    </div>
                    <div className="h-2.5 w-3/4 rounded bg-slate-200/40" />
                    <div className="h-2.5 w-1/2 rounded bg-slate-200/40" />
                  </div>
                </li>
              ))}
            </ul>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center px-6 py-12 text-center">
              <div className="w-10 h-10 rounded-full glass-subtle flex items-center justify-center text-slate-400 mb-3">
                <InboxIcon className="w-5 h-5" />
              </div>
              <p className="text-[13px] font-medium text-slate-700">Nothing recent</p>
              <p className="text-[12px] text-slate-500 mt-0.5">
                Connect Gmail from the Inbox page to see messages here.
              </p>
            </div>
          ) : (
            <ul className="p-2 space-y-0.5">
              {messages.map((m, idx) => {
                const name = formatFrom(m.from_email || m.from || "");
                const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
                const [bg, fg] = getAvatarColors(name);
                const subject = m.subject || "(no subject)";
                const snippet = m.snippet || m.preview || "";
                const date = formatDate(m.date || m.internal_date || m.received_at);
                const threadId = m.thread_id || m.threadId || m.id;
                return (
                  <li key={m.id || threadId || idx}>
                    <button
                      type="button"
                      onClick={() => openReader(m)}
                      className="w-full text-left flex items-start gap-3 px-3 py-2.5 rounded-xl hover:bg-white/55 transition-colors group focus:outline-none focus:ring-2 focus:ring-accent-300"
                    >
                      <div
                        className={`w-8 h-8 rounded-full ${bg} ${fg} flex items-center justify-center font-bold text-[13px] flex-shrink-0`}
                      >
                        {initial}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-[13px] font-semibold text-slate-900 truncate">
                            {name}
                          </span>
                          <span className="text-[11px] text-slate-500 flex-shrink-0 tabular-nums">
                            {date}
                          </span>
                        </div>
                        <p className="text-[12.5px] text-slate-700 truncate mt-0.5">
                          {subject}
                        </p>
                        {snippet && (
                          <p className="text-[11.5px] text-slate-500 truncate">
                            {snippet}
                          </p>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      {openMsg && (
        <MailReader
          message={openMsg}
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={closeReader}
        />
      )}
    </div>
  );
}
