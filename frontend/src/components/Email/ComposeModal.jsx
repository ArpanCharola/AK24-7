import { useState } from "react";
import { X, Sparkles, Send } from "lucide-react";
import { emailApi } from "../../services/api";

export default function ComposeModal({ onClose }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [intent, setIntent] = useState("");
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState(null);

  async function generate() {
    if (!intent.trim()) return;
    setGenerating(true);
    setNote(null);
    try {
      const { data } = await emailApi.compose({
        purpose: "outreach",
        last_message: intent,
        to: to || null,
        company: subject || null,
      });
      setBody(data.body || "");
      if (!subject && data.subject) setSubject(data.subject);
    } catch {
      setNote("Couldn't draft the email.");
    } finally {
      setGenerating(false);
    }
  }

  async function send() {
    setSending(true);
    setNote(null);
    try {
      await emailApi.send({ to, subject, body });
      onClose();
    } catch (error) {
      setNote(error?.response?.data?.detail || "Send failed — reconnect Gmail to grant send permission.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/30 backdrop-blur-sm sm:items-center sm:justify-end sm:p-4">
      <div className="glass-strong flex max-h-[85vh] w-full flex-col rounded-2xl sm:w-[520px]">
        <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold">New message</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close compose window"><X size={16} /></button>
        </div>
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-4">
          <input value={to} onChange={(event) => setTo(event.target.value)} placeholder="To" className="w-full border-b border-border bg-transparent pb-2 text-[13px] text-foreground outline-none" />
          <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" className="w-full border-b border-border bg-transparent pb-2 text-[13px] text-foreground outline-none" />
          <div className="flex gap-2 pt-1">
            <input value={intent} onChange={(event) => setIntent(event.target.value)} placeholder="What do you want to say?" className="input-glass flex-1 !py-2 text-[12px]" />
            <button onClick={generate} disabled={generating || !intent.trim()} className="btn-secondary !px-3 !py-2 text-[12px]">
              <Sparkles size={12} /> {generating ? "…" : "Generate"}
            </button>
          </div>
          <textarea value={body} onChange={(event) => setBody(event.target.value)} rows={8} placeholder="Write your email…" className="input-glass flex-1 resize-none text-[13px]" />
          {note && <p className="text-[12px] text-danger">{note}</p>}
        </div>
        <div className="flex shrink-0 justify-end gap-2 border-t border-border px-4 py-3">
          <button onClick={onClose} className="btn-secondary text-[13px]">Discard</button>
          <button onClick={send} disabled={sending || !to.trim() || !body.trim()} className="btn-primary text-[13px]">
            <Send size={14} /> {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
