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
      // Backend AI drafter is context-driven; pass the user's intent as the
      // message context and let it produce a professional outreach draft.
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
    } catch (e) {
      setNote(e?.response?.data?.detail || "Send failed — reconnect Gmail to grant send permission.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:justify-end bg-black/30 backdrop-blur-sm sm:p-4">
      <div className="glass-strong rounded-2xl w-full sm:w-[520px] flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
          <h3 className="text-sm font-semibold">New message</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
        </div>

        <div className="flex flex-col gap-2 p-4 flex-1 overflow-y-auto">
          <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="To"
                 className="w-full border-b border-border pb-2 text-[13px] bg-transparent outline-none text-foreground" />
          <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject"
                 className="w-full border-b border-border pb-2 text-[13px] bg-transparent outline-none text-foreground" />

          <div className="flex gap-2 pt-1">
            <input value={intent} onChange={(e) => setIntent(e.target.value)} placeholder="What do you want to say?"
                   className="flex-1 text-[12px] input-glass !py-2" />
            <button onClick={generate} disabled={generating || !intent.trim()} className="btn-secondary !py-2 !px-3 text-[12px]">
              <Sparkles size={12} /> {generating ? "…" : "Generate"}
            </button>
          </div>

          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={8} placeholder="Write your email…"
                    className="flex-1 text-[13px] input-glass resize-none" />
          {note && <p className="text-[12px] text-danger">{note}</p>}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t border-border shrink-0">
          <button onClick={onClose} className="btn-secondary text-[13px]">Discard</button>
          <button onClick={send} disabled={sending || !to.trim() || !body.trim()} className="btn-primary text-[13px]">
            <Send size={14} /> {sending ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
