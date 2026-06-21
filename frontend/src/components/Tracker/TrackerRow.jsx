import { useState, useRef, useEffect } from "react";
import { X, ExternalLink } from "lucide-react";
import StatusDropdown from "./StatusDropdown";
import { INDIA_CITIES } from "../../lib/india-cities";

const PORTALS = ["Wellfound", "LinkedIn", "Indeed", "Naukri", "Instahyre", "Company Site", "Others"];
const JOB_TYPES = ["Remote", "Hybrid", "Onsite"];

function InlineCell({ value, onCommit, placeholder = "—", type = "text", bold = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");

  function commit() {
    setEditing(false);
    if (draft !== (value ?? "")) onCommit(draft);
  }

  if (editing) {
    return (
      <input
        autoFocus
        type={type}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
        className="w-full bg-brand/5 border border-brand/40 rounded px-1 py-0.5 text-[12px] outline-none text-foreground"
      />
    );
  }
  return (
    <span
      onClick={() => { setDraft(value ?? ""); setEditing(true); }}
      className={`block cursor-text text-[12px] rounded px-1 py-0.5 hover:bg-muted/60 truncate ${
        value ? (bold ? "font-medium text-foreground" : "text-foreground") : "text-muted-foreground/50"
      }`}
    >
      {value || placeholder}
    </span>
  );
}

function SelectCell({ value, options, onCommit, placeholder = "—" }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);
  useEffect(() => {
    function h(e) { if (!ref.current?.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const filtered = options.filter((o) => o.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="relative" ref={ref}>
      <span
        onClick={() => setOpen((o) => !o)}
        className={`block cursor-pointer text-[12px] rounded px-1 py-0.5 hover:bg-muted/60 truncate ${value ? "text-foreground" : "text-muted-foreground/50"}`}
      >
        {value || placeholder}
      </span>
      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 glass-strong rounded-xl overflow-hidden min-w-[140px] max-h-52 flex flex-col">
          {options.length > 8 && (
            <input
              autoFocus value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="px-2 py-1.5 text-[12px] bg-transparent border-b border-border outline-none text-foreground"
            />
          )}
          <div className="overflow-y-auto">
            {filtered.map((opt) => (
              <button
                key={opt}
                onClick={() => { onCommit(opt); setOpen(false); setSearch(""); }}
                className="flex w-full items-center px-3 py-1.5 text-[12px] text-foreground hover:bg-muted transition-colors"
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// One spreadsheet row. Every cell commits a single-field PATCH via onUpdate.
export default function TrackerRow({ row, index, onUpdate, onDelete }) {
  const patch = (field) => (val) => onUpdate(row.id, { [field]: val });

  return (
    <tr className="group border-b border-border hover:bg-muted/20 transition-colors align-middle">
      <td className="px-3 py-2 text-[11px] text-muted-foreground text-center w-10">{index + 1}</td>
      <td className="px-2 py-2 min-w-[150px]"><InlineCell value={row.company} onCommit={patch("company")} placeholder="Company" bold /></td>
      <td className="px-2 py-2 min-w-[130px]"><InlineCell value={row.role} onCommit={patch("role")} placeholder="Role" /></td>
      <td className="px-2 py-2 min-w-[110px]"><SelectCell value={row.job_portal} options={PORTALS} onCommit={patch("job_portal")} placeholder="Portal" /></td>
      <td className="px-2 py-2 min-w-[110px]"><SelectCell value={row.location} options={[...INDIA_CITIES, "Other"]} onCommit={patch("location")} placeholder="Location" /></td>
      <td className="px-2 py-2 min-w-[90px]"><InlineCell value={row.salary} onCommit={patch("salary")} placeholder="Salary" /></td>
      <td className="px-2 py-2 min-w-[90px]"><SelectCell value={row.job_type} options={JOB_TYPES} onCommit={patch("job_type")} placeholder="Type" /></td>
      <td className="px-2 py-2 min-w-[90px]"><InlineCell value={row.resume_label} onCommit={patch("resume_label")} placeholder="Resume" /></td>
      <td className="px-2 py-2 min-w-[80px]">
        {row.job_link ? (
          <a href={row.job_link} target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1 text-[12px] text-brand hover:underline">
            <ExternalLink size={11} /> Link
          </a>
        ) : (
          <InlineCell value={row.job_link} onCommit={patch("job_link")} placeholder="URL" type="url" />
        )}
      </td>
      <td className="px-2 py-2 min-w-[110px]"><StatusDropdown value={row.status} onChange={patch("status")} /></td>
      <td className="px-2 py-2 min-w-[160px]"><InlineCell value={row.notes} onCommit={patch("notes")} placeholder="Notes" /></td>
      <td className="px-2 py-2 min-w-[110px]"><InlineCell value={row.contact} onCommit={patch("contact")} placeholder="Contacts" /></td>
      <td className="px-2 py-2 w-8">
        <button
          onClick={() => onDelete(row.id)}
          className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-danger transition-all"
          title="Delete row"
        >
          <X size={14} />
        </button>
      </td>
    </tr>
  );
}
