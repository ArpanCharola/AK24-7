import { senderName, timeAgo } from "../../lib/format";

const KIND_BADGE = {
  confirmed: { label: "Applied", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200" },
  assessment: { label: "Assessment", cls: "bg-sky-100 text-sky-800 dark:bg-sky-400/15 dark:text-sky-200" },
  interview: { label: "Interview", cls: "bg-blue-100 text-blue-800 dark:bg-blue-400/15 dark:text-blue-200" },
  offer: { label: "Offer", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200" },
  rejected: { label: "Rejected", cls: "bg-slate-200 text-slate-700 dark:bg-slate-400/15 dark:text-slate-200" },
};

export default function EmailList({ messages, activeId, onSelect, loading }) {
  if (loading) {
    return (
      <div className="divide-y divide-border">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="space-y-2 px-4 py-3.5">
            <div className="h-3 w-1/3 rounded bg-muted animate-pulse" />
            <div className="h-3 w-2/3 rounded bg-muted animate-pulse" />
          </div>
        ))}
      </div>
    );
  }

  if (!messages?.length) {
    return <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">No messages here.</div>;
  }

  return (
    <div className="divide-y divide-border/80">
      {messages.map((m) => {
        const badge = KIND_BADGE[m.kind];
        const isInteractive = typeof onSelect === "function";
        const rowClass = `flex w-full flex-col gap-1 px-4 py-3.5 text-left transition-colors ${
          isInteractive ? "hover:bg-muted/40" : "cursor-default"
        } ${activeId === m.id ? "bg-brand/5" : ""}`;
        const content = (
          <>
            <div className="flex items-center gap-2">
              <span className="truncate text-[13px] font-semibold text-foreground">{senderName(m.from_email)}</span>
              <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{timeAgo(m.date)}</span>
            </div>
            <p className="truncate text-[12.5px] text-foreground/90">{m.subject || "(no subject)"}</p>
            <div className="flex items-center gap-2">
              <p className="flex-1 truncate text-[11.5px] text-muted-foreground">{m.snippet}</p>
              {badge && <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${badge.cls}`}>{badge.label}</span>}
            </div>
          </>
        );

        if (!isInteractive) {
          return (
            <div key={m.id} className={rowClass}>
              {content}
            </div>
          );
        }

        return (
          <button key={m.id} onClick={() => onSelect(m)} className={rowClass}>
            {content}
          </button>
        );
      })}
    </div>
  );
}
