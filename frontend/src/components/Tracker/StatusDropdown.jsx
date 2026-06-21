import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

// Status values MUST match backend ALLOWED_STATUSES exactly (note "to apply"
// has a space and is lowercase).
export const STATUSES = [
  { value: "to apply",   label: "To Apply",   cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-500/20 dark:text-yellow-300" },
  { value: "applied",    label: "Applied",    cls: "bg-teal-100 text-teal-800 dark:bg-teal-500/20 dark:text-teal-300" },
  { value: "assessment", label: "Assessment", cls: "bg-green-100 text-green-800 dark:bg-green-500/20 dark:text-green-300" },
  { value: "interview",  label: "Interview",  cls: "bg-blue-100 text-blue-800 dark:bg-blue-500/20 dark:text-blue-300" },
  { value: "offer",      label: "Offer",      cls: "bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-300" },
  { value: "rejected",   label: "Rejected",   cls: "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300" },
];

export default function StatusDropdown({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const current = STATUSES.find((s) => s.value === value) ?? STATUSES[1];

  useEffect(() => {
    function h(e) { if (!ref.current?.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold ${current.cls}`}
      >
        {current.label}
        <ChevronDown size={10} />
      </button>
      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 glass-strong rounded-xl overflow-hidden min-w-[130px] p-1">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              onClick={() => { onChange(s.value); setOpen(false); }}
              className="flex w-full items-center px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
            >
              <span className={`px-2 py-0.5 rounded-md text-[11px] font-semibold ${s.cls}`}>{s.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
