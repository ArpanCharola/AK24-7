import { useState } from "react";
import { X, PlusCircle } from "lucide-react";
import api from "../../services/api";
import { senderName, senderAddress } from "../../lib/format";

function readerDocument(bodyHtml) {
  return `<!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <base target="_blank" />
        <style>
          :root { color-scheme: light; }
          * { box-sizing: border-box; max-width: 100% !important; }
          html, body { min-height: 100%; margin: 0; }
          body { overflow-wrap: anywhere; background: #f5f8fc; color: #14243d; font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: clamp(16px, 2vw, 24px); }
          body > *:first-child { margin-top: 0 !important; }
          img, video, table, iframe { max-width: 100% !important; height: auto !important; }
          table { width: 100% !important; border-collapse: collapse; }
          td, th { max-width: 100%; }
          a { color: #0f6b54; text-decoration: underline; }
          pre, code { white-space: pre-wrap; overflow-wrap: anywhere; }
          blockquote { margin: 1rem 0; padding-left: 1rem; border-left: 3px solid #c8d5e4; color: #4d6078; }
        </style>
      </head>
      <body>${bodyHtml}</body>
    </html>`;
}

function EmailBody({ message, className = "" }) {
  if (message.body_html) {
    return (
      <iframe
        srcDoc={readerDocument(message.body_html)}
        sandbox=""
        title="Email body"
        className={`h-full w-full rounded-xl border border-border bg-white shadow-sm ${className}`.trim()}
      />
    );
  }

  return (
    <article className={`h-full overflow-y-auto rounded-xl border border-border bg-card p-5 text-[14px] leading-7 text-foreground shadow-sm ${className}`.trim()}>
      <p className="whitespace-pre-wrap">{message.body_text || message.snippet || "This message has no readable content."}</p>
    </article>
  );
}

export default function EmailDetail({ message, onClose, onAddedToTracker }) {
  const [note, setNote] = useState(null);

  const from = senderAddress(message.from_email);
  const isJobRelated = !!message.kind;

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
    <>
      <section className="flex h-full min-h-0 flex-1 flex-col bg-card" aria-label="Message reader">
        <header className="flex shrink-0 items-start gap-3 border-b border-border px-4 py-3.5">
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-[14px] font-semibold leading-5 text-foreground">{message.subject || "(no subject)"}</p>
            <p className="mt-1 truncate text-[12px] text-muted-foreground">
              {senderName(message.from_email)} <span aria-hidden="true">·</span> {from}
            </p>
          </div>
          {isJobRelated && (
            <button onClick={addToTracker} className="btn-secondary shrink-0 !px-2.5 !py-1 text-[11px]" title="Add to Job Tracker">
              <PlusCircle size={12} /> Track
            </button>
          )}
          <button onClick={onClose} className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close message">
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-hidden bg-muted/30 p-3 sm:p-4">
          <EmailBody message={message} className="min-h-full" />
        </div>

        {note && (
          <footer className="shrink-0 border-t border-border bg-card px-4 py-3 text-[11.5px] text-muted-foreground">
            {note}
          </footer>
        )}
      </section>

    </>
  );
}
