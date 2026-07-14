import { useMemo, useState } from "react";
import { X, Sparkles, Send, AlertCircle } from "lucide-react";
import { emailApi } from "../../services/api";

function companyFromEmail(email) {
  const domain = String(email || "").split("@")[1] || "";
  const base = domain.split(".")[0] || "";
  if (!base) return null;
  return base.charAt(0).toUpperCase() + base.slice(1);
}

export default function ComposeModal({ onClose, onSent, canSend = true, needsReconnect = false }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState(null);

  const canGenerate = useMemo(
    () => Boolean(to.trim() || subject.trim() || body.trim()),
    [to, subject, body]
  );

  async function generate() {
    if (!canGenerate) return;
    setGenerating(true);
    setNote(null);
    try {
      const { data } = await emailApi.compose({
        purpose: "outreach",
        to: to.trim() || null,
        company: companyFromEmail(to.trim()),
        role: subject.trim() || null,
        last_message: body.trim() || subject.trim() || null,
      });
      if (data.to) setTo(data.to);
      if (data.subject) setSubject(data.subject);
      setBody(data.body || "");
      setNote("Draft generated. Review it, then send.");
    } catch (error) {
      setNote(error?.response?.data?.detail || "Couldn't draft the email.");
    } finally {
      setGenerating(false);
    }
  }

  async function send() {
    if (!canSend) {
      setNote("Reconnect Gmail to grant send permission before sending.");
      return;
    }
    setSending(true);
    setNote(null);
    try {
      const payload = {
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        kind: "compose",
      };
      const { data } = await emailApi.send(payload);
      if (data?.dry_run) {
        setNote("Message logged as a dry run on the server.");
        return;
      }
      onSent?.({ to: payload.to, subject: payload.subject });
      onClose();
    } catch (error) {
      setNote(error?.response?.data?.detail || "Send failed — reconnect Gmail to grant send permission.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-slate-950/55 p-4 backdrop-blur-md sm:p-6">
      <div className="glass-strong flex h-[min(88vh,760px)] w-full max-w-3xl flex-col overflow-hidden rounded-[32px] border border-border bg-card shadow-[0_50px_140px_-56px_rgba(15,23,42,0.58)]">
        <div className="sticky top-0 z-10 flex shrink-0 items-center justify-between border-b border-border bg-card px-5 py-4 sm:px-6">
          <div>
            <h3 className="text-base font-semibold text-foreground">Compose email</h3>
            <p className="mt-1 text-[12px] text-muted-foreground">Simple popup card — just write, generate, and send.</p>
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close compose window">
            <X size={16} />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-5 sm:p-6">
          {needsReconnect && (
            <div className="flex items-start gap-2 rounded-2xl border border-warning/30 bg-warning/10 px-3 py-2.5 text-[11.5px] text-warning">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <span>Gmail is connected, but send permission is missing. You can still generate a draft, then reconnect to send.</span>
            </div>
          )}

          <div className="grid gap-4">
            <label className="space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">To</span>
              <input value={to} onChange={(event) => setTo(event.target.value)} placeholder="recruiter@company.com" className="input-glass !py-3" />
            </label>

            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <label className="space-y-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Subject</span>
                <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject line" className="input-glass !py-3" />
              </label>
              <button onClick={generate} disabled={generating || !canGenerate} className="btn-secondary !rounded-full !px-4 !py-3 text-[12px] font-semibold">
                <Sparkles size={13} /> {generating ? "Generating…" : "Generate draft"}
              </button>
            </div>

            <label className="flex min-h-0 flex-1 flex-col space-y-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Message</span>
              <textarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                rows={16}
                placeholder="Write your message here. Or enter To / Subject and click Generate draft."
                className="input-glass min-h-[340px] resize-none text-[13px] leading-6"
              />
            </label>
          </div>

          {note && <p className="text-[12px] text-muted-foreground">{note}</p>}
        </div>

        <div className="sticky bottom-0 z-10 flex shrink-0 justify-end gap-2 border-t border-border bg-card px-5 py-4 sm:px-6">
          <button onClick={onClose} className="btn-secondary !rounded-full text-[13px]">Discard</button>
          <button onClick={send} disabled={sending || !to.trim() || !subject.trim() || !body.trim() || !canSend} className="btn-primary !rounded-full text-[13px]">
            <Send size={14} /> {sending ? "Sending…" : "Send email"}
          </button>
        </div>
      </div>
    </div>
  );
}
