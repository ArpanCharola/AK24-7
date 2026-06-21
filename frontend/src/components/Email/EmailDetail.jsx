import { useState } from "react";
import { X, Sparkles, Send, PlusCircle } from "lucide-react";
import api, { emailApi } from "../../services/api";
import { senderName, senderAddress } from "../../lib/format";

export default function EmailDetail({ message, onClose, onAddedToTracker }) {
  const [reply, setReply] = useState("");
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [note, setNote] = useState(null);

  const from = senderAddress(message.from_email);
  const isJobRelated = !!message.kind;

  async function generate() {
    setGenerating(true);
    try {
      const { data } = await emailApi.compose({
        purpose: "reply",
        recipient_name: senderName(message.from_email),
        last_message: message.body_text || message.snippet || "",
        to: from,
        company: senderName(message.from_email),
      });
      setReply(data.body || "");
    } catch {
      setNote("Couldn't draft a reply.");
    } finally {
      setGenerating(false);
    }
  }

  async function send() {
    setSending(true);
    setNote(null);
    try {
      await emailApi.send({
        to: from,
        subject: message.subject?.startsWith("Re:") ? message.subject : `Re: ${message.subject || ""}`,
        body: reply,
        thread_id: message.thread_id,
      });
      setNote("Reply sent.");
      setReply("");
    } catch (e) {
      setNote(e?.response?.data?.detail || "Send failed — reconnect Gmail to grant send permission.");
    } finally {
      setSending(false);
    }
  }

  async function addToTracker() {
    try {
      await api.post("/saved-applications/", {
        company: senderName(message.from_email),
        role: message.subject || "Role not specified",
        applied_at: message.date ? new Date(message.date).toISOString() : new Date().toISOString(),
        status: "applied",
        mail_url: `https://mail.google.com/mail/u/0/#inbox/${message.thread_id}`,
      });
      setNote("Added to Job Tracker.");
      onAddedToTracker?.();
    } catch {
      setNote("Couldn't add to tracker.");
    }
  }

  return (
    <div className="flex flex-col h-full border-l border-border bg-card">
      <div className="flex items-start gap-3 px-4 py-3 border-b border-border shrink-0">
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-semibold text-foreground truncate">{message.subject || "(no subject)"}</p>
          <p className="text-[12px] text-muted-foreground mt-0.5 truncate">
            {senderName(message.from_email)} · {from}
          </p>
        </div>
        {isJobRelated && (
          <button onClick={addToTracker} className="btn-secondary !py-1 !px-2 text-[11px] shrink-0" title="Add to Job Tracker">
            <PlusCircle size={12} /> Track
          </button>
        )}
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground shrink-0"><X size={16} /></button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {message.body_html ? (
          <iframe srcDoc={message.body_html} sandbox="allow-same-origin" title="Email body"
                  className="w-full min-h-[280px] border-none bg-white rounded-lg" />
        ) : (
          <pre className="text-[13px] text-foreground whitespace-pre-wrap font-sans">{message.body_text || message.snippet}</pre>
        )}
      </div>

      <div className="border-t border-border p-3 space-y-2 shrink-0">
        {note && <p className="text-[11.5px] text-muted-foreground">{note}</p>}
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Reply</span>
          <button onClick={generate} disabled={generating} className="btn-secondary !py-1 !px-2.5 text-[11px]">
            <Sparkles size={12} /> {generating ? "Drafting…" : "Generate with AI"}
          </button>
        </div>
        <textarea
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          rows={4}
          placeholder="Write a reply, or generate one with AI…"
          className="w-full text-[13px] input-glass resize-none"
        />
        <button onClick={send} disabled={sending || !reply.trim()} className="btn-primary !py-1.5 !px-3 text-[12px]">
          <Send size={13} /> {sending ? "Sending…" : "Send reply"}
        </button>
      </div>
    </div>
  );
}
