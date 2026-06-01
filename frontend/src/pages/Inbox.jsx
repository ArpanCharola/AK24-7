import { useCallback, useEffect, useRef, useState } from "react";
import api from "../services/api";

/** Page size. Matches Gmail's default web inbox so the counter reads
 *  "1–100 of N" identically. Backend caps at 100. */
const PAGE_SIZE = 100;

// tiny classname joiner (aiapply ships no cn() util)
const cx = (...parts) => parts.filter(Boolean).join(" ");

// ─── helpers (ported from source) ────────────────────────────────────────────

const AVATAR_PALETTE = [
  ["#dbeafe", "#1d4ed8"], ["#f3e8ff", "#7c3aed"], ["#fce7f3", "#be185d"],
  ["#dcfce7", "#15803d"], ["#fff7ed", "#c2410c"], ["#fef9c3", "#a16207"],
];
function getAvatarColors(name) {
  if (!name || name.length === 0) return ["#f1f5f9", "#64748b"];
  return AVATAR_PALETTE[name.charCodeAt(0) % AVATAR_PALETTE.length] || ["#f1f5f9", "#64748b"];
}

function formatFrom(raw) {
  if (!raw) return "Unknown";
  const m = raw.match(/^"?([^"<]+)"?\s*<[^>]+>$/);
  return m ? m[1].trim() : raw.split("@")[0] || raw || "Unknown";
}

// Pulls the bare address out of `Name <a@b.com>`.
function extractEmail(raw) {
  if (!raw) return "";
  const m = raw.match(/<([^>]+)>/);
  return m ? m[1] : raw;
}

function formatDate(raw) {
  try {
    const d = new Date(raw);
    const now = new Date();
    const diff = Math.floor((now.getTime() - d.getTime()) / 86400000);
    if (diff === 0) return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    if (diff === 1) return "Yesterday";
    if (diff < 7) return d.toLocaleDateString("en-US", { weekday: "long" });
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return raw;
  }
}

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return err?.message || fallback;
}

// Gmail deep links.
const gmailThread = (threadId) => `https://mail.google.com/mail/u/0/#inbox/${threadId}`;
const gmailCompose = (from, subject) =>
  `https://mail.google.com/mail/u/0/?view=cm&to=${encodeURIComponent(extractEmail(from))}&su=Re%3A+${encodeURIComponent(subject || "")}`;

// ─── inline icons (no lucide-react) ──────────────────────────────────────────

const Icon = ({ d, lines, className = "h-4 w-4", strokeWidth = 2 }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor"
       strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
    {d && <path d={d} />}
    {lines}
  </svg>
);
const IconChevronLeft = (p) => <Icon {...p} d="M15 18l-6-6 6-6" />;
const IconChevronRight = (p) => <Icon {...p} d="M9 18l6-6-6-6" />;
const IconRefresh = (p) => (
  <Icon {...p} lines={<>
    <polyline points="23 4 23 10 17 10" />
    <polyline points="1 20 1 14 7 14" />
    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
    <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
  </>} />
);
const IconClose = (p) => (
  <Icon {...p} lines={<><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>} />
);
const IconExternal = (p) => (
  <Icon {...p} lines={<>
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </>} />
);
const IconReply = (p) => (
  <Icon {...p} lines={<><polyline points="9 17 4 12 9 7" /><path d="M20 18v-2a4 4 0 0 0-4-4H4" /></>} />
);
const IconInbox = (p) => (
  <Icon {...p} lines={<>
    <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </>} />
);

// ─── skeleton ─────────────────────────────────────────────────────────────────

function MailListSkeleton({ rows = 10 }) {
  return (
    <div className="flex-1 overflow-hidden">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-5 py-3.5 border-l-[3px] border-l-transparent border-b border-slate-200">
          <div className="flex items-start gap-3">
            <div className="h-8 w-8 rounded-full bg-slate-200/60 animate-pulse flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
              <div className="flex justify-between gap-2">
                <div className="h-3 w-40 bg-slate-200/60 rounded animate-pulse" />
                <div className="h-3 w-12 bg-slate-200/50 rounded animate-pulse" />
              </div>
              <div className="h-2.5 w-2/3 bg-slate-200/50 rounded animate-pulse" />
              <div className="h-2.5 w-1/2 bg-slate-200/40 rounded animate-pulse" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── page ─────────────────────────────────────────────────────────────────────

// Wrap a Gmail HTML body so links open in a new tab and the iframe gets a
// readable default style. We render in a sandboxed iframe so scripts/styles
// from foreign senders can't touch the host page.
function wrapBodyHtml(html) {
  return `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">
<style>
  html,body{margin:0;padding:12px 16px;color:#0f172a;font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;word-wrap:break-word;}
  img{max-width:100%;height:auto;}
  a{color:#7c3aed;}
  blockquote{margin:8px 0;padding-left:12px;border-left:3px solid #e2e8f0;color:#475569;}
  pre,code{white-space:pre-wrap;word-break:break-word;}
  table{max-width:100%;}
</style>
</head><body>${html || ""}</body></html>`;
}

export default function Inbox() {
  const [emails, setEmails] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [firstLoadDone, setFirstLoadDone] = useState(false);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Reader pane: full body fetched on row click.
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [bodyHeight, setBodyHeight] = useState(400);
  const detailReqId = useRef(0);
  const iframeRef = useRef(null);

  // Pagination state.
  //   pageTokens = stack of page tokens used to REACH the current page from page 1.
  //     - page 1: []   page 2: [tokenForPage2]   page 3: [tokenForPage2, tokenForPage3]
  //   nextToken = the token to advance to the NEXT page (null on the last page).
  //   total = backend's resultSizeEstimate, used for the "of N" suffix.
  const [pageTokens, setPageTokens] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const [total, setTotal] = useState(0);

  // Guards a fetch against a newer one having superseded it (mount cleanup /
  // overlapping refresh). Each fetch stamps its own id; only the latest commits.
  const reqId = useRef(0);

  const fetchPage = useCallback(async ({ pageToken = null, fresh = false } = {}) => {
    const id = ++reqId.current;
    try {
      const params = { limit: PAGE_SIZE };
      if (pageToken) params.page_token = pageToken;
      if (fresh) params.fresh = true;
      const { data } = await api.get("/email/inbox", { params });
      if (id !== reqId.current) return;
      setEmails(data?.messages || []);
      setNextToken(data?.next_page_token || null);
      setTotal(data?.total_estimate || 0);
      setError(null);
    } catch (e) {
      if (id !== reqId.current) return;
      setError(errorMessage(e, "Failed to load inbox."));
      setEmails([]);
      setNextToken(null);
    } finally {
      if (id === reqId.current) {
        setLoading(false);
        setFirstLoadDone(true);
      }
    }
  }, []);

  // Page 1 on mount. The JWT is auto-attached by services/api.js and the
  // ConsentGate has already cleared by the time this renders.
  useEffect(() => {
    void fetchPage({ pageToken: null });
  }, [fetchPage]);

  // Fetch the full body whenever the selected row changes.
  useEffect(() => {
    if (!selected?.id) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    const id = ++detailReqId.current;
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    setBodyHeight(400);
    (async () => {
      try {
        const { data } = await api.get(`/email/message/${encodeURIComponent(selected.id)}`);
        if (id !== detailReqId.current) return;
        setDetail(data || null);
      } catch (e) {
        if (id !== detailReqId.current) return;
        setDetailError(errorMessage(e, "Failed to load this message."));
      } finally {
        if (id === detailReqId.current) setDetailLoading(false);
      }
    })();
  }, [selected?.id]);

  const onBodyIframeLoad = () => {
    try {
      const doc = iframeRef.current?.contentDocument;
      if (!doc?.body) return;
      const h = Math.min(Math.max(doc.body.scrollHeight + 24, 220), 4000);
      setBodyHeight(h);
    } catch {
      // srcDoc keeps us same-origin, so this shouldn't throw — defensive only.
    }
  };

  const pageNumber = pageTokens.length + 1;
  const pageStart = (pageNumber - 1) * PAGE_SIZE + 1;
  const pageEnd = pageStart + emails.length - 1;

  const canPrev = pageTokens.length > 0 && !loading;
  const canNext = !!nextToken && !loading;

  const handleNext = () => {
    if (!canNext) return;
    const tok = nextToken;
    setPageTokens((s) => [...s, tok]);
    setSelected(null);
    setLoading(true);
    setError(null);
    void fetchPage({ pageToken: tok });
  };

  const handlePrev = () => {
    if (!canPrev) return;
    const newStack = pageTokens.slice(0, -1);
    setPageTokens(newStack);
    setSelected(null);
    setLoading(true);
    setError(null);
    // newStack's last entry is the token for the page we're going BACK to;
    // an empty stack means page 1 (no token).
    void fetchPage({ pageToken: newStack[newStack.length - 1] ?? null });
  };

  const handleRefresh = async () => {
    if (refreshing || loading) return;
    setRefreshing(true);
    setLoading(true);
    setError(null);
    setSelected(null);
    // Refresh the CURRENT page (whatever token got us here), bypassing cache.
    const currentToken = pageTokens[pageTokens.length - 1] ?? null;
    await fetchPage({ pageToken: currentToken, fresh: true });
    setRefreshing(false);
  };

  // Hidden until the first page resolves so it never flashes "1–0 of 0".
  const showCounter = firstLoadDone && !error && emails.length > 0;
  const spinning = loading || refreshing;

  return (
    <div className="flex flex-col h-full overflow-hidden animate-fade-in">

      {/* Sticky top bar — counter + Prev/Next + Refresh, right-aligned. */}
      <div className="shrink-0 sticky top-0 z-10 flex items-center justify-end gap-4 py-3 px-1 border-b border-slate-200">
        {showCounter && (
          <span className="text-[12px] text-slate-500 tabular-nums select-none">
            <span className="text-slate-900 font-medium">{pageStart.toLocaleString()}</span>
            <span className="mx-0.5">–</span>
            <span className="text-slate-900 font-medium">{pageEnd.toLocaleString()}</span>
            {total > 0 && (
              <>
                <span className="mx-1.5">of</span>
                <span className="text-slate-900 font-medium">{total.toLocaleString()}</span>
              </>
            )}
          </span>
        )}

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handlePrev}
            disabled={!canPrev}
            aria-label="Newer messages"
            className={cx(
              "h-8 w-8 inline-flex items-center justify-center rounded-full border border-slate-200 text-slate-500 transition-colors",
              canPrev ? "hover:text-slate-900 hover:bg-white/55" : "opacity-30 cursor-default"
            )}
          >
            <IconChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleNext}
            disabled={!canNext}
            aria-label="Older messages"
            className={cx(
              "h-8 w-8 inline-flex items-center justify-center rounded-full border border-slate-200 text-slate-500 transition-colors",
              canNext ? "hover:text-slate-900 hover:bg-white/55" : "opacity-30 cursor-default"
            )}
          >
            <IconChevronRight className="h-4 w-4" />
          </button>
        </div>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={spinning}
          aria-label="Refresh"
          className={cx(
            "h-8 w-8 inline-flex items-center justify-center rounded-full border border-slate-200 text-slate-500 transition-colors",
            spinning ? "opacity-40 cursor-default" : "hover:text-slate-900 hover:bg-white/55"
          )}
        >
          <IconRefresh className={cx("h-3.5 w-3.5", spinning && "animate-spin")} />
        </button>
      </div>

      {/* Two-pane content — fills remaining viewport. */}
      <div className="flex flex-1 gap-4 overflow-hidden pt-4">

        {/* LEFT — list (~48% on md+; hidden once a row is selected on mobile). */}
        <div className={cx(
          "flex flex-col overflow-hidden glass rounded-2xl transition-all duration-200",
          selected ? "hidden md:flex md:w-[48%]" : "w-full"
        )}>
          {loading && !firstLoadDone ? (
            <MailListSkeleton rows={10} />
          ) : error ? (
            <div className="m-4 glass-subtle rounded-2xl px-4 py-4 flex items-start gap-3">
              <svg className="h-5 w-5 text-rose-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-[14px] font-semibold text-rose-600">Could not load inbox</p>
                <p className="text-[13px] text-slate-500 mt-1">{error}</p>
              </div>
            </div>
          ) : emails.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2.5 text-slate-400">
              <IconInbox className="h-10 w-10 opacity-40" strokeWidth={1.5} />
              <p className="text-[13px]">Your inbox is empty</p>
            </div>
          ) : (
            <ul className="flex-1 overflow-y-auto">
              {emails.map((m) => {
                const name = formatFrom(m.from_email);
                const [bg, fg] = getAvatarColors(name);
                const isActive = selected?.id === m.id;
                const isUnread = Array.isArray(m.label_ids) && m.label_ids.includes("UNREAD");
                return (
                  <li
                    key={m.id}
                    onClick={() => setSelected(isActive ? null : m)}
                    className={cx(
                      "px-5 py-3.5 border-b border-slate-200 border-l-[3px] cursor-pointer transition-colors duration-100",
                      isActive ? "bg-white/55 border-l-accent-500" : "border-l-transparent hover:bg-white/30"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className="h-8 w-8 flex-shrink-0 rounded-full flex items-center justify-center text-[12px] font-bold uppercase mt-0.5"
                        style={{ background: bg, color: fg }}
                      >
                        {name.charAt(0)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <span className={cx("truncate text-[13px] text-slate-900", isUnread ? "font-bold" : "font-semibold")}>
                            {name}
                          </span>
                          <span className="flex-shrink-0 text-[11px] text-slate-500 tabular-nums">{formatDate(m.date)}</span>
                        </div>
                        <p className={cx("truncate text-[12px]", isUnread ? "font-semibold text-slate-900" : "text-slate-900/75")}>
                          {m.subject || "(no subject)"}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <p className="truncate text-[11px] text-slate-500 flex-1">{m.snippet}</p>
                          {isUnread && <span className="h-1.5 w-1.5 rounded-full flex-shrink-0 bg-accent-500" />}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* RIGHT — reader pane (~52%). Reads from `selected` directly, no fetch. */}
        {selected && (
          <div className="flex-1 flex flex-col overflow-hidden glass rounded-2xl w-full md:w-auto">

            {/* Header — avatar + sender + email + Gmail link + close. */}
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-4 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className="h-9 w-9 flex-shrink-0 rounded-full flex items-center justify-center text-[13px] font-bold uppercase"
                  style={(() => {
                    const [bg, fg] = getAvatarColors(formatFrom(selected.from_email));
                    return { background: bg, color: fg };
                  })()}
                >
                  {formatFrom(selected.from_email).charAt(0)}
                </div>
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold text-slate-900 truncate">{formatFrom(selected.from_email)}</p>
                  <p className="text-[12px] text-slate-500 truncate">{extractEmail(selected.from_email)}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <a
                  href={gmailThread(selected.thread_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Open thread in Gmail"
                  className="flex items-center gap-1.5 text-[12px] font-medium text-slate-500 hover:text-slate-900 no-underline px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-white/55 transition-colors"
                >
                  <IconExternal className="h-3.5 w-3.5" />
                  Gmail
                </a>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  aria-label="Close"
                  className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-slate-500 hover:text-slate-900 hover:bg-white/55 transition-colors"
                >
                  <IconClose className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Subject + To/Date metadata. */}
            <div className="px-5 py-3 border-b border-slate-200 shrink-0">
              <h2 className="text-[15px] font-semibold text-slate-900 leading-snug">{selected.subject || "(no subject)"}</h2>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[11px] text-slate-500">
                {selected.to_email && (
                  <span><span className="uppercase tracking-wide text-[10px] font-semibold text-slate-900/40">To</span> {selected.to_email}</span>
                )}
                {selected.date && (
                  <span><span className="uppercase tracking-wide text-[10px] font-semibold text-slate-900/40">Date</span> {formatDate(selected.date)}</span>
                )}
              </div>
            </div>

            {/* Body — full HTML in a sandboxed iframe, with text/snippet fallbacks. */}
            <div className="flex-1 overflow-y-auto px-2 py-2">
              {detailLoading ? (
                <div className="space-y-2 px-3 py-2">
                  <div className="h-3 w-5/6 bg-slate-200/60 rounded animate-pulse" />
                  <div className="h-3 w-2/3 bg-slate-200/50 rounded animate-pulse" />
                  <div className="h-3 w-4/5 bg-slate-200/50 rounded animate-pulse" />
                  <div className="h-3 w-1/2 bg-slate-200/40 rounded animate-pulse" />
                  <div className="h-3 w-3/4 bg-slate-200/40 rounded animate-pulse" />
                </div>
              ) : detailError ? (
                <div className="m-2 glass-subtle rounded-xl px-4 py-3">
                  <p className="text-[13px] font-semibold text-rose-600">Couldn't open this message</p>
                  <p className="text-[12px] text-slate-500 mt-0.5">{detailError}</p>
                  <p className="text-[12px] text-slate-500 mt-2">
                    Showing the preview snippet. <a href={gmailThread(selected.thread_id)} target="_blank" rel="noopener noreferrer" className="text-accent-600 font-semibold hover:underline">Open in Gmail →</a>
                  </p>
                  <p className="text-[13px] leading-[1.7] whitespace-pre-wrap text-slate-900 mt-3 px-1">{selected.snippet}</p>
                </div>
              ) : detail?.body_html ? (
                <iframe
                  ref={iframeRef}
                  title="email body"
                  sandbox="allow-same-origin allow-popups"
                  srcDoc={wrapBodyHtml(detail.body_html)}
                  onLoad={onBodyIframeLoad}
                  style={{ width: "100%", height: bodyHeight, border: "0", background: "transparent" }}
                />
              ) : detail?.body_text ? (
                <p className="text-[13px] leading-[1.75] whitespace-pre-wrap text-slate-900 px-3 py-2">{detail.body_text}</p>
              ) : (
                <p className="text-[13px] leading-[1.75] whitespace-pre-wrap text-slate-900 px-3 py-2">{selected.snippet}</p>
              )}
              <a
                href={gmailThread(selected.thread_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mx-3 mt-3 text-[12px] text-accent-600 font-semibold hover:underline"
              >
                Open full email in Gmail →
              </a>
            </div>

            {/* Action bar — Reply (compose deep link) + Open thread. */}
            <div className="px-5 py-3 border-t border-slate-200 flex gap-2.5 shrink-0">
              <a
                href={gmailCompose(selected.from_email, selected.subject)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 h-[36px] px-4 rounded-full text-[13px] font-semibold bg-accent-500 text-white hover:opacity-90 no-underline transition-opacity"
              >
                <IconReply className="h-3.5 w-3.5" />
                Reply
              </a>
              <a
                href={gmailThread(selected.thread_id)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 h-[36px] px-4 rounded-full text-[13px] font-medium text-slate-900 border border-slate-200 hover:bg-white/55 no-underline transition-colors"
              >
                <IconExternal className="h-3.5 w-3.5" />
                Open thread
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
