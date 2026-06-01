import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { emailApi } from "../services/api";
import {
  useEmailStatus, useLabels, useConnectEmail, useScanEmail,
  useComposeEmail, useSendEmail,
} from "../hooks/useEmail";
import EmailChipInput, { parseRecipientsFromPrompt } from "../components/EmailChipInput";

const KIND_CONFIG = {
  confirmed:  { label: "Confirmed",  cls: "bg-emerald-100/80 text-emerald-700" },
  assessment: { label: "Assessment", cls: "bg-violet-100/80 text-violet-700" },
  interview:  { label: "Interview",  cls: "bg-sky-100/80 text-sky-700" },
  offer:      { label: "Offer",      cls: "bg-amber-100/90 text-amber-700" },
  rejected:   { label: "Rejected",   cls: "bg-slate-200/70 text-slate-500" },
};

function senderName(from) {
  if (!from) return "(unknown)";
  const m = from.match(/^\s*"?([^"<]+?)"?\s*</);
  if (m) return m[1].trim();
  const a = from.match(/<([^>]+)>/);
  return (a ? a[1] : from).trim();
}
function fmtDate(raw) {
  if (!raw) return "";
  const d = new Date(raw);
  if (isNaN(d)) return "";
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
                 : d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function EmailAuto() {
  const { data: status, refetch: refetchStatus } = useEmailStatus();
  const connected = !!status?.connected;
  const { data: labels } = useLabels(connected);
  const { mutate: connect, isPending: connecting } = useConnectEmail();
  const { mutate: scan, isPending: scanning, data: scanResult } = useScanEmail();
  const compose = useComposeEmail();
  const send = useSendEmail();

  const [messages, setMessages] = useState([]);
  const [nextToken, setNextToken] = useState(null);
  const nextTokenRef = useRef(null);  // mirrors nextToken so loadPage can stay stable
  const [activeLabel, setActiveLabel] = useState(null);
  const [loadingInbox, setLoadingInbox] = useState(false);

  // Reader pane: the clicked row + the full body fetched on open.
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  async function openReader(m) {
    if (selected?.id === m.id) { closeReader(); return; }
    setSelected(m);
    setDetail(null);
    setDetailError(null);
    if (!m.id) {
      setDetailError("This message can't be opened — no message id.");
      return;
    }
    setDetailLoading(true);
    try {
      const r = await emailApi.message(m.id);
      setDetail(r?.data || null);
    } catch (e) {
      setDetailError(e?.response?.data?.detail || e?.message || "Failed to load this message.");
    } finally {
      setDetailLoading(false);
    }
  }

  function closeReader() {
    setSelected(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
  }

  const loadPage = useCallback(async (reset, label) => {
    setLoadingInbox(true);
    try {
      // Read the page token from a ref, not the closure, so this callback stays
      // stable and "Load more" always uses the current token (no stale paging).
      const pageToken = reset ? undefined : nextTokenRef.current;
      const r = await emailApi.inbox({ limit: 25, pageToken, label });
      const msgs = r?.data?.messages || [];  // tolerate a missing/null messages field
      setMessages((prev) => (reset ? msgs : [...prev, ...msgs]));
      const next = r?.data?.next_page_token || null;
      nextTokenRef.current = next;
      setNextToken(next);
    } finally {
      setLoadingInbox(false);
    }
  }, []);

  useEffect(() => {
    if (connected) loadPage(true, activeLabel);
  }, [connected, activeLabel, loadPage]);

  const selectLabel = (id) => { closeReader(); setActiveLabel(id); };

  const counts = messages.reduce((a, m) => { if (m.kind) a[m.kind] = (a[m.kind] || 0) + 1; return a; }, {});

  // ── Compose (inline chip-based panel) ──────────────────────────────────
  const [composeOpen, setComposeOpen] = useState(false);
  const [toEmails, setToEmails] = useState([]);
  const [ccEmails, setCcEmails] = useState([]);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [composeKind, setComposeKind] = useState("follow_up");
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResult, setAiResult] = useState(null);
  const [toast, setToast] = useState(null);
  const resultRef = useRef(null);

  const showToast = (msg, ms = 4500) => {
    setToast(msg);
    setTimeout(() => setToast(null), ms);
  };

  const moveBetweenFields = (email, from, to) => {
    if (from === to) return;
    if (from === "to") setToEmails((prev) => prev.filter((e) => e.toLowerCase() !== email.toLowerCase()));
    else setCcEmails((prev) => prev.filter((e) => e.toLowerCase() !== email.toLowerCase()));
    if (to === "to") {
      setToEmails((prev) =>
        prev.some((e) => e.toLowerCase() === email.toLowerCase()) ? prev : [...prev, email],
      );
    } else {
      setCcEmails((prev) =>
        prev.some((e) => e.toLowerCase() === email.toLowerCase()) ? prev : [...prev, email],
      );
    }
  };

  const applyPromptRecipients = (prompt) => {
    const { to, cc } = parseRecipientsFromPrompt(prompt);
    let added = 0;
    if (to.length) {
      setToEmails((prev) => {
        const seen = new Set(prev.map((e) => e.toLowerCase()));
        const next = [...prev];
        for (const e of to) {
          if (!seen.has(e.toLowerCase())) {
            next.push(e);
            seen.add(e.toLowerCase());
            added++;
          }
        }
        return next;
      });
    }
    if (cc.length) {
      setCcEmails((prev) => {
        const seen = new Set(prev.map((e) => e.toLowerCase()));
        const next = [...prev];
        for (const e of cc) {
          if (!seen.has(e.toLowerCase())) {
            next.push(e);
            seen.add(e.toLowerCase());
            added++;
          }
        }
        return next;
      });
    }
    return added;
  };

  function openComposePanel(purpose = "follow_up", prefill = {}) {
    setComposeOpen(true);
    setComposeKind(purpose);
    if (prefill.to) {
      setToEmails((prev) =>
        prev.some((e) => e.toLowerCase() === prefill.to.toLowerCase()) ? prev : [...prev, prefill.to],
      );
    }
    // Seed body via AI immediately when the user came from a Reply button.
    if (prefill.last_message) {
      setAiPrompt(prefill.last_message);
      void handleGenerate(purpose, prefill.last_message);
    }
    // Outreach from DiscoveredJobs: ground the draft via discovered_job_id so
    // /email/compose populates company/role/recipient_name from the saved row.
    if (prefill.discovered_job_id || (purpose === "outreach" && (prefill.company || prefill.role))) {
      const ctxPrompt = `Cold outreach about the ${prefill.role || "role"} at ${prefill.company || "the company"}.`;
      setAiPrompt(ctxPrompt);
      (async () => {
        try {
          const d = await compose.mutateAsync({
            purpose,
            discovered_job_id: prefill.discovered_job_id,
            company: prefill.company,
            role: prefill.role,
            to: prefill.to,
          });
          setAiResult({ subject: d.subject || "", body: d.body || "" });
          if (d.to) {
            setToEmails((prev) =>
              prev.some((e) => e.toLowerCase() === d.to.toLowerCase()) ? prev : [...prev, d.to],
            );
          }
        } catch {
          showToast("Couldn't draft — write it yourself.");
        }
      })();
    }
  }

  // ── Auto-open compose when arriving via "Reach out" from DiscoveredJobs ───
  // Triggered once per visit; clears query params after firing so refresh
  // doesn't loop the panel open.
  const [searchParams, setSearchParams] = useSearchParams();
  const autoComposeFiredRef = useRef(false);
  useEffect(() => {
    if (autoComposeFiredRef.current) return;
    if (!connected) return;
    const jobId = searchParams.get("job_id");
    const to = searchParams.get("to");
    if (!jobId && !to) return;
    autoComposeFiredRef.current = true;
    openComposePanel("outreach", {
      to: to || undefined,
      discovered_job_id: jobId ? Number(jobId) : undefined,
      company: searchParams.get("company") || undefined,
      role: searchParams.get("role") || undefined,
    });
    const next = new URLSearchParams(searchParams);
    ["job_id", "to", "company", "role"].forEach((k) => next.delete(k));
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);

  async function handleGenerate(purpose = composeKind, promptOverride) {
    const prompt = (promptOverride ?? aiPrompt).trim();
    if (!prompt) {
      showToast("Describe the email first.");
      return;
    }
    setAiResult(null);
    const added = applyPromptRecipients(prompt);
    if (added > 0) {
      showToast(`Found ${added} recipient${added === 1 ? "" : "s"} in your prompt`, 1800);
    }
    try {
      const d = await compose.mutateAsync({ purpose, last_message: prompt });
      const next = { subject: d.subject || "", body: d.body || "" };
      setAiResult(next);
      if (d.to) {
        setToEmails((prev) =>
          prev.some((e) => e.toLowerCase() === d.to.toLowerCase()) ? prev : [...prev, d.to],
        );
      }
    } catch {
      showToast("Couldn't generate — try again or write it yourself.");
    }
  }

  function applyAIToForm() {
    if (!aiResult) return;
    setSubject(aiResult.subject);
    setBody(aiResult.body);
    applyPromptRecipients(aiPrompt);
    showToast("AI draft applied", 1800);
  }

  async function submitSend() {
    if (toEmails.length === 0 || !subject.trim() || !body.trim()) {
      showToast("Please fill in To, Subject, and Body.");
      return;
    }
    try {
      const res = await send.mutateAsync({
        to: toEmails.join(", "),
        cc: ccEmails.length ? ccEmails.join(", ") : null,
        subject,
        body,
        kind: composeKind,
      });
      showToast(res.dry_run ? "Dry-run: email logged, not sent." : "Email sent ✓");
      setToEmails([]);
      setCcEmails([]);
      setSubject("");
      setBody("");
      setAiPrompt("");
      setAiResult(null);
    } catch (e) {
      showToast(e?.response?.data?.detail || "Send failed", 6000);
    }
  }

  function handleConnect() {
    connect(undefined, { onSuccess: (url) => { window.location.href = url; } });
  }

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">email-auto</h1>
          <p className="text-[13px] text-slate-500 mt-0.5">Auto-tagged inbox · AI compose & send · labels</p>
        </div>
        {connected && (
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-slate-500 hidden md:inline">{status.gmail_email}</span>
            <button onClick={() => setComposeOpen((v) => !v)} className="btn-primary !py-1.5 !px-3 text-[12px]">
              {composeOpen ? "✕ Close" : "✎ Compose"}
            </button>
            <button onClick={() => scan()} disabled={scanning} className="btn-secondary !py-1.5 !px-3 text-[12px]">{scanning ? "Scanning…" : "Scan"}</button>
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto">
        {toast && <div className="m-3 px-3 py-2 rounded-xl text-[13px] glass-subtle text-slate-700">{toast}</div>}

        {!connected ? (
          <div className="max-w-md mx-auto text-center px-6 py-20">
            <p className="text-[15px] font-semibold text-slate-800">Connect your inbox</p>
            <p className="text-[13px] text-slate-500 mt-1.5 mb-5">Sign in with Google (or connect from Profile) to auto-tag, label, and follow up on your job mail.</p>
            <button onClick={handleConnect} disabled={connecting} className="btn-secondary">{connecting ? "Opening…" : "Connect Gmail"}</button>
          </div>
        ) : (
          <div className="px-4 py-3">
            {composeOpen && (
              <ComposePanel
                kind={composeKind}
                setKind={setComposeKind}
                toEmails={toEmails}
                ccEmails={ccEmails}
                setToEmails={setToEmails}
                setCcEmails={setCcEmails}
                moveBetweenFields={moveBetweenFields}
                subject={subject}
                setSubject={setSubject}
                body={body}
                setBody={setBody}
                aiPrompt={aiPrompt}
                setAiPrompt={setAiPrompt}
                aiResult={aiResult}
                resultRef={resultRef}
                onGenerate={() => handleGenerate()}
                onApplyAI={applyAIToForm}
                onSend={submitSend}
                generating={compose.isPending}
                sending={send.isPending}
              />
            )}
            {/* Reconnect banner */}
            {status.needs_reconnect && (
              <div className="mb-3 px-4 py-2.5 rounded-xl bg-amber-50 text-amber-800 text-[12.5px] flex items-center justify-between gap-3">
                <span>Reconnect Gmail to enable labels &amp; sending (your current grant is read-only).</span>
                <button onClick={handleConnect} className="font-semibold underline whitespace-nowrap">Reconnect</button>
              </div>
            )}

            {/* Summary + scan result */}
            {Object.keys(counts).length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 px-1 pb-2">
                {Object.keys(KIND_CONFIG).filter((k) => counts[k]).map((k) => (
                  <span key={k} className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${KIND_CONFIG[k].cls}`}>
                    {KIND_CONFIG[k].label} <span className="opacity-70">{counts[k]}</span>
                  </span>
                ))}
              </div>
            )}
            {scanResult && <p className="px-1 pb-2 text-[11.5px] text-slate-400">Scan: {scanResult.matched} matched · {scanResult.updated} updated · {scanResult.labeled} labeled.</p>}

            <div className="flex gap-3">
              {/* Labels rail */}
              <div className="w-40 flex-shrink-0 hidden sm:block">
                <button onClick={() => selectLabel(null)}
                  className={`block w-full text-left px-2.5 py-1.5 rounded-lg text-[12px] ${!activeLabel ? "bg-accent-100/70 text-accent-700 font-semibold" : "text-slate-600 hover:bg-white/55"}`}>
                  Inbox
                </button>
                {(labels || []).filter((l) => l.type === "user").map((l) => (
                  <button key={l.id} onClick={() => selectLabel(l.id)} title={l.name}
                    className={`block w-full text-left px-2.5 py-1.5 rounded-lg text-[12px] truncate ${activeLabel === l.id ? "bg-accent-100/70 text-accent-700 font-semibold" : "text-slate-600 hover:bg-white/55"}`}>
                    {l.name}
                  </button>
                ))}
              </div>

              {/* Messages list — narrows when a mail is open (hidden on mobile while reading) */}
              <div className={`min-w-0 ${selected ? "hidden md:block md:w-[40%] flex-shrink-0" : "flex-1"}`}>
                {messages.length === 0 && !loadingInbox ? (
                  <p className="text-center text-slate-400 text-sm py-12">No mail here.</p>
                ) : (
                  <ul className="space-y-1">
                    {messages.map((m) => {
                      const kc = m.kind && KIND_CONFIG[m.kind];
                      const isActive = selected?.id === m.id;
                      return (
                        <li key={m.id}
                          onClick={() => openReader(m)}
                          className={`group px-3 py-2.5 rounded-xl cursor-pointer transition-colors border-l-[3px] ${isActive ? "bg-white/60 border-l-accent-500" : "border-l-transparent hover:bg-white/55"}`}>
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-[13px] font-semibold text-slate-800 truncate max-w-[160px]">{senderName(m.from_email)}</span>
                              {kc && <span className={`flex-shrink-0 px-1.5 py-0.5 rounded-md text-[9.5px] font-bold ${kc.cls}`}>{kc.label}</span>}
                            </div>
                            <div className="flex items-center gap-2 flex-shrink-0">
                              <button onClick={(e) => { e.stopPropagation(); openComposePanel("reply", { to: m.from_email, last_message: `${m.subject}\n${m.snippet}` }); }}
                                className="opacity-0 group-hover:opacity-100 text-[11px] text-accent-600 font-semibold transition-opacity">Reply</button>
                              <span className="text-[11px] text-slate-400">{fmtDate(m.date)}</span>
                            </div>
                          </div>
                          <p className="text-[12.5px] text-slate-700 truncate mt-0.5">{m.subject}</p>
                          <p className="text-[11.5px] text-slate-400 truncate">{m.snippet}</p>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {nextToken && (
                  <div className="text-center py-3">
                    <button onClick={() => loadPage(false, activeLabel)} disabled={loadingInbox}
                      className="btn-secondary !py-1.5 !px-4 text-[12px]">{loadingInbox ? "Loading…" : "Load more"}</button>
                  </div>
                )}
              </div>

              {/* Reader pane — full body of the clicked mail */}
              {selected && (
                <MailReaderPane
                  message={selected}
                  detail={detail}
                  loading={detailLoading}
                  error={detailError}
                  onClose={closeReader}
                  onReply={() => openComposePanel("reply", { to: selected.from_email, last_message: `${selected.subject}\n${selected.snippet}` })}
                />
              )}
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

// Right-hand reading pane. HTML bodies render inside a fully-sandboxed iframe
// (no scripts, no same-origin) so remote markup can't touch the app; plain-text
// falls back to a pre-wrapped block. "Open in new tab" deep-links the Gmail thread.
function MailReaderPane({ message, detail, loading, error, onClose, onReply }) {
  const subject = message.subject || "(no subject)";
  const threadId = message.thread_id || message.threadId || message.id;
  const gmailHref = threadId
    ? `https://mail.google.com/mail/u/0/#inbox/${threadId}`
    : "https://mail.google.com/mail/u/0/#inbox";

  const html = detail?.body_html;
  const text = detail?.body_text || detail?.snippet || message.snippet || "";

  return (
    <div className="flex-1 min-w-0 flex flex-col glass-subtle rounded-2xl overflow-hidden self-start max-h-[calc(100vh-220px)]">
      <header className="flex-shrink-0 flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-200">
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-slate-900 break-words">{subject}</p>
          <p className="text-[12.5px] text-slate-500 truncate mt-0.5">
            {senderName(message.from_email)}
            {message.date ? ` · ${fmtDate(message.date)}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <a href={gmailHref} target="_blank" rel="noopener noreferrer" title="Open in new tab"
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12px] font-semibold text-accent-600 hover:text-accent-700 hover:bg-white/55 transition-colors">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14 5h5v5m0-5L10 14M19 14v5a1 1 0 01-1 1H6a1 1 0 01-1-1V7a1 1 0 011-1h5" />
            </svg>
            Open in new tab
          </a>
          <button type="button" onClick={onClose} aria-label="Close"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-white/55 transition-colors">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
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
          <div className="m-4 px-3.5 py-2.5 rounded-xl bg-rose-50 border border-rose-200 text-[12.5px] text-rose-700">{error}</div>
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

      <footer className="flex-shrink-0 flex items-center gap-2.5 px-5 py-3 border-t border-slate-200">
        <button onClick={onReply} className="btn-primary !py-1.5 !px-4 text-[13px]">Reply</button>
        <a href={gmailHref} target="_blank" rel="noopener noreferrer"
          className="text-[12px] font-medium text-slate-600 hover:text-slate-900 transition-colors">Open in Gmail ↗</a>
      </footer>
    </div>
  );
}

function ComposePanel({
  kind, setKind, toEmails, ccEmails, setToEmails, setCcEmails, moveBetweenFields,
  subject, setSubject, body, setBody, aiPrompt, setAiPrompt, aiResult, resultRef,
  onGenerate, onApplyAI, onSend, generating, sending,
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-4 mb-4">
      {/* FORM panel */}
      <div className="glass-subtle rounded-2xl overflow-hidden">
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[13px] font-semibold text-slate-900">Compose</h3>
            <div className="flex gap-1">
              {["follow_up", "thank_you", "reply"].map((p) => (
                <button
                  key={p}
                  onClick={() => setKind(p)}
                  className={`px-2 py-0.5 rounded-md text-[11px] ${
                    kind === p
                      ? "bg-accent-100 text-accent-700 font-semibold"
                      : "text-slate-500 hover:bg-white/60"
                  }`}
                >
                  {p.replace("_", " ")}
                </button>
              ))}
            </div>
          </div>

          <EmailChipInput
            label="To"
            fieldId="to"
            values={toEmails}
            onChange={setToEmails}
            onAcceptDrop={(email, from) => moveBetweenFields(email, from, "to")}
            placeholder="recipient@example.com  (Enter to add)"
          />
          <EmailChipInput
            label="CC"
            fieldId="cc"
            values={ccEmails}
            onChange={setCcEmails}
            onAcceptDrop={(email, from) => moveBetweenFields(email, from, "cc")}
            placeholder="Drag a chip here or type"
          />

          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-1">
              Subject
            </label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject"
              className="h-[38px] rounded-full border border-slate-200 focus:border-slate-400 outline-none px-4 bg-white/55 text-[13px] text-slate-900"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-1">
              Body
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your email here…"
              rows={8}
              className="min-h-[200px] rounded-2xl border border-slate-200 focus:border-slate-400 outline-none p-4 resize-y bg-white/55 text-[13px] text-slate-900"
            />
          </div>
        </div>

        <div className="px-5 py-3 bg-white/40 border-t border-slate-200 flex items-center justify-between">
          <button
            onClick={onSend}
            disabled={sending}
            className="btn-primary !py-1.5 !px-4 text-[13px]"
          >
            {sending ? "Sending…" : "Send Now"}
          </button>
          <span className="text-[12px] text-slate-500">
            {body.trim() ? body.trim().split(/\s+/).length : 0} words
          </span>
        </div>
      </div>

      {/* AI panel */}
      <div className="glass-subtle rounded-2xl p-5 space-y-4 h-fit">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-[9px] bg-accent-100 text-accent-600">
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4M4 19h4M13 3l3 6 6 3-6 3-3 6-3-6-6-3 6-3 3-6z" />
            </svg>
          </span>
          <h2 className="text-[14px] font-semibold text-slate-900">AI Generate</h2>
        </div>

        <textarea
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
          placeholder="Describe the email…   e.g. To: arc21@gmail.com — follow up on the project demo"
          rows={4}
          className="w-full h-[110px] rounded-2xl border border-slate-200 focus:border-slate-400 outline-none p-3 resize-none bg-white/55 text-[13px] text-slate-900"
        />

        <p className="text-[11px] text-slate-500 leading-[1.5] px-1">
          Tip: include <code className="text-slate-900 font-mono">To: name@example.com</code> or{" "}
          <code className="text-slate-900 font-mono">CC: name@example.com</code> in your prompt and we&apos;ll
          auto-fill those fields. Drag chips between To and CC anytime.
        </p>

        <button
          onClick={() => onGenerate()}
          disabled={generating}
          className="w-full btn-primary !py-1.5 text-[13px]"
        >
          {generating ? "Generating…" : "✨ Generate with AI"}
        </button>

        {generating && (
          <div className="pt-4 border-t border-slate-200 space-y-2">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Writing your draft…
            </p>
            <div className="p-3 bg-white/55 rounded-md border border-slate-200 space-y-2">
              <div className="h-3 w-3/4 bg-slate-200/60 rounded animate-pulse" />
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-2.5 bg-slate-200/40 rounded animate-pulse" style={{ width: `${90 - i * 8}%` }} />
              ))}
            </div>
          </div>
        )}

        {aiResult && !generating && (
          <div ref={resultRef} className="pt-4 border-t border-slate-200 space-y-2 animate-fade-in">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Generated result
            </p>
            <div className="p-3 bg-white/55 rounded-md border border-slate-200">
              <p className="text-[12px] text-slate-900 truncate mb-1">
                <span className="font-semibold">Subject:</span> {aiResult.subject}
              </p>
              <p className="text-[12px] text-slate-500 line-clamp-4">{aiResult.body}</p>
            </div>
            <button
              onClick={onApplyAI}
              className="flex items-center gap-1.5 text-[13px] text-slate-900 font-semibold hover:gap-2 transition-all"
            >
              Apply to form
              <span aria-hidden>→</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
