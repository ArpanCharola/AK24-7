import { useState } from "react";
import { Inbox, Star, Send, File, AlertCircle, Ban, Plus, Tag, PenLine } from "lucide-react";
import NewLabelDialog from "./NewLabelDialog";

// System folders map to Gmail's built-in label ids passed to /email/inbox?label=.
const SYSTEM_FOLDERS = [
  { id: "INBOX",     label: "Inbox",     icon: Inbox },
  { id: "STARRED",   label: "Starred",   icon: Star },
  { id: "SENT",      label: "Sent",      icon: Send },
  { id: "DRAFT",     label: "Drafts",    icon: File },
  { id: "IMPORTANT", label: "Important", icon: AlertCircle },
  { id: "SPAM",      label: "Spam",      icon: Ban },
];

export default function EmailSidebar({ active, onSelect, userLabels = [], onCompose, onLabelCreated }) {
  const [showNew, setShowNew] = useState(false);

  const itemCls = (on) =>
    `flex items-center gap-3 w-full px-3 py-2 rounded-xl text-[13px] transition-colors ${
      on ? "bg-brand/10 text-brand font-semibold" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
    }`;

  return (
    <aside className="hidden h-full w-56 shrink-0 flex-col overflow-y-auto border-r border-border bg-sidebar/60 lg:flex">
      <div className="p-3">
        <button onClick={onCompose} className="btn-gradient w-full !rounded-full !py-2.5 text-[13px]">
          <PenLine size={15} /> Compose
        </button>
      </div>

      <nav className="px-2 space-y-0.5">
        {SYSTEM_FOLDERS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => onSelect(id)} className={itemCls(active === id)}>
            <Icon size={16} strokeWidth={1.75} /> {label}
          </button>
        ))}
      </nav>

      <div className="px-3 pt-4 pb-1 flex items-center justify-between">
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Labels</span>
        <button onClick={() => setShowNew(true)} className="text-muted-foreground hover:text-foreground" title="New label">
          <Plus size={14} />
        </button>
      </div>
      <nav className="px-2 space-y-0.5 pb-3">
        {userLabels.length === 0 && (
          <p className="px-3 py-1 text-[11.5px] text-muted-foreground/70">No custom labels yet.</p>
        )}
        {userLabels.map((l) => (
          <button key={l.id} onClick={() => onSelect(`label:${l.id}`)} className={itemCls(active === `label:${l.id}`)}>
            <Tag size={13} strokeWidth={1.75} />
            <span className="truncate">{l.name}</span>
          </button>
        ))}
      </nav>

      {showNew && (
        <NewLabelDialog
          userLabels={userLabels}
          onClose={() => setShowNew(false)}
          onCreated={() => { setShowNew(false); onLabelCreated?.(); }}
        />
      )}
    </aside>
  );
}
