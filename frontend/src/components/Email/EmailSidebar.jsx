import { useState } from "react";
import { Inbox, Star, Send, File, AlertCircle, Ban, Plus, Tag } from "lucide-react";
import NewLabelDialog from "./NewLabelDialog";

const SYSTEM_FOLDERS = [
  { id: "INBOX", label: "Inbox", icon: Inbox },
  { id: "STARRED", label: "Starred", icon: Star },
  { id: "SENT", label: "Sent", icon: Send },
  { id: "DRAFT", label: "Drafts", icon: File },
  { id: "IMPORTANT", label: "Important", icon: AlertCircle },
  { id: "SPAM", label: "Spam", icon: Ban },
];

export default function EmailSidebar({ active, onSelect, userLabels = [], onLabelCreated }) {
  const [showNew, setShowNew] = useState(false);

  const itemCls = (on) =>
    `flex items-center gap-3 w-full rounded-2xl px-3 py-2.5 text-[13px] transition-colors ${
      on ? "bg-brand/10 text-brand font-semibold shadow-sm" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
    }`;

  return (
    <aside className="sidebar-panel hidden h-full w-60 shrink-0 flex-col overflow-y-auto lg:flex">
      <div className="border-b border-border/80 px-3 py-4">
        <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Mailbox</p>
      </div>

      <div className="px-3 py-3">
        <nav className="space-y-1">
          {SYSTEM_FOLDERS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => onSelect(id)} className={itemCls(active === id)}>
              <Icon size={16} strokeWidth={1.75} /> {label}
            </button>
          ))}
        </nav>
      </div>

      <div className="mt-auto border-t border-border/80 px-3 py-3">
        <div className="flex items-center justify-between px-2 pb-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Labels</span>
          <button onClick={() => setShowNew(true)} className="text-muted-foreground transition-colors hover:text-foreground" title="New label">
            <Plus size={14} />
          </button>
        </div>
        <nav className="space-y-1">
          {userLabels.length === 0 && <p className="px-3 py-1 text-[11.5px] text-muted-foreground/70">No custom labels yet.</p>}
          {userLabels.map((l) => (
            <button key={l.id} onClick={() => onSelect(`label:${l.id}`)} className={itemCls(active === `label:${l.id}`)}>
              <Tag size={13} strokeWidth={1.75} />
              <span className="truncate">{l.name}</span>
            </button>
          ))}
        </nav>
      </div>

      {showNew && (
        <NewLabelDialog
          userLabels={userLabels}
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            onLabelCreated?.();
          }}
        />
      )}
    </aside>
  );
}
