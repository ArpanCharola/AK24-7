import { useState } from "react";

// Comma/Enter-separated tag editor for skills, preferred locations, etc.
export default function TagInput({ value = [], onChange, placeholder }) {
  const [draft, setDraft] = useState("");

  function add(raw) {
    const parts = raw.split(",").map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    const next = [...value];
    for (const p of parts) if (!next.some((t) => t.toLowerCase() === p.toLowerCase())) next.push(p);
    onChange(next);
    setDraft("");
  }

  function remove(idx) {
    onChange(value.filter((_, i) => i !== idx));
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 input-glass !h-auto min-h-[42px] py-2">
      {value.map((tag, i) => (
        <span key={i} className="pill border bg-accent-100/80 text-accent-700 border-accent-200/60">
          {tag}
          <button type="button" onClick={() => remove(i)} className="ml-0.5 text-slate-400 hover:text-rose-500">×</button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(draft);
          } else if (e.key === "Backspace" && !draft && value.length) {
            remove(value.length - 1);
          }
        }}
        onBlur={() => draft && add(draft)}
        placeholder={value.length ? "" : placeholder}
        className="flex-1 min-w-[120px] bg-transparent outline-none text-[13px] text-slate-800 placeholder:text-slate-400"
      />
    </div>
  );
}
