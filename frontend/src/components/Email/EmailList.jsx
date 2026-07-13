import { senderName, timeAgo } from "../../lib/format";

const KIND_BADGE = {
  confirmed:  { label: "Applied",    cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200" },
  assessment: { label: "Assessment", cls: "bg-sky-100 text-sky-800 dark:bg-sky-400/15 dark:text-sky-200" },
  interview:  { label: "Interview",  cls: "bg-blue-100 text-blue-800 dark:bg-blue-400/15 dark:text-blue-200" },
  offer:      { label: "Offer",      cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-200" },
  rejected:   { label: "Rejected",   cls: "bg-slate-200 text-slate-700 dark:bg-slate-400/15 dark:text-slate-200" },
};

export default function EmailList({ messages, activeId, onSelect, loading }) {
  if (loading) {
    return (
      <div className="divide-y divide-border">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="px-4 py-3 space-y-1.5">
            <div className="h-3 bg-muted animate-pulse rounded w-1/3" />
            <div className="h-3 bg-muted animate-pulse rounded w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  if (!messages?.length) {
    return <div className="flex items-center justify-center h-full text-[13px] text-muted-foreground">No messages here.</div>;
  }

  return (
    <div className="divide-y divide-border">
      {messages.map((m) => {
        const badge = KIND_BADGE[m.kind];
        return (
          <button
            key={m.id}
            onClick={() => onSelect(m)}
            className={`flex flex-col gap-0.5 w-full px-4 py-3 text-left hover:bg-muted/40 transition-colors ${
              activeId === m.id ? "bg-brand/5" : ""
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold text-foreground truncate">{senderName(m.from_email)}</span>
              <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{timeAgo(m.date)}</span>
            </div>
            <p className="text-[12.5px] text-foreground/90 truncate">{m.subject || "(no subject)"}</p>
            <div className="flex items-center gap-2">
              <p className="text-[11.5px] text-muted-foreground truncate flex-1">{m.snippet}</p>
              {badge && (
                <span className={`shrink-0 px-1.5 py-0.5 rounded-md text-[10px] font-semibold ${badge.cls}`}>{badge.label}</span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
