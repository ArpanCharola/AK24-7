import { senderName, timeAgo } from "../../lib/format";

const KIND_BADGE = {
  confirmed:  { label: "Applied",    cls: "bg-green-100 text-green-800 dark:bg-green-500/20 dark:text-green-300" },
  assessment: { label: "Assessment", cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-300" },
  interview:  { label: "Interview",  cls: "bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-300" },
  offer:      { label: "Offer",      cls: "bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-300" },
  rejected:   { label: "Rejected",   cls: "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300" },
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
