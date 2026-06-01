import { useRef, useState } from "react";

const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

export function parseRecipientsFromPrompt(text) {
  const out = { to: [], cc: [] };
  if (!text) return out;
  const lines = text.split(/[\n\r;]+/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const toMatch = line.match(/^\s*to\s*[:=-]\s*(.+)$/i);
    const ccMatch = line.match(/^\s*cc\s*[:=-]\s*(.+)$/i);
    if (toMatch) {
      const emails = toMatch[1].match(EMAIL_RE) || [];
      out.to.push(...emails);
    } else if (ccMatch) {
      const emails = ccMatch[1].match(EMAIL_RE) || [];
      out.cc.push(...emails);
    }
  }
  const seenTo = new Set();
  const seenCc = new Set();
  out.to = out.to.filter((e) => {
    const k = e.toLowerCase();
    if (seenTo.has(k)) return false;
    seenTo.add(k);
    return true;
  });
  out.cc = out.cc.filter((e) => {
    const k = e.toLowerCase();
    if (seenCc.has(k)) return false;
    seenCc.add(k);
    return true;
  });
  return out;
}

function isValidEmail(s) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

export function EmailChipInput({
  label,
  fieldId,
  values,
  onChange,
  onAcceptDrop,
  placeholder,
}) {
  const [draft, setDraft] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const addEmails = (input) => {
    const candidates = input
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (candidates.length === 0) return;
    const next = [...values];
    const seen = new Set(next.map((v) => v.toLowerCase()));
    for (const c of candidates) {
      if (!isValidEmail(c)) continue;
      const k = c.toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      next.push(c);
    }
    if (next.length !== values.length) onChange(next);
  };

  const removeAt = (i) => {
    const next = values.slice();
    next.splice(i, 1);
    onChange(next);
  };

  const handleKey = (e) => {
    if (e.key === "Enter" || e.key === "," || (e.key === " " && draft.includes("@"))) {
      e.preventDefault();
      if (draft.trim()) {
        addEmails(draft);
        setDraft("");
      }
    } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
      removeAt(values.length - 1);
    }
  };

  const handleBlur = () => {
    if (draft.trim()) {
      addEmails(draft);
      setDraft("");
    }
  };

  const handleDragStart = (e, email) => {
    e.dataTransfer.setData(
      "application/x-email-chip",
      JSON.stringify({ email, from: fieldId }),
    );
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e) => {
    if (Array.from(e.dataTransfer.types).includes("application/x-email-chip")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setDragOver(true);
    }
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const raw = e.dataTransfer.getData("application/x-email-chip");
    if (!raw) return;
    try {
      const { email, from } = JSON.parse(raw);
      if (email && from && from !== fieldId && typeof onAcceptDrop === "function") {
        onAcceptDrop(email, from);
      }
    } catch {
      // ignore malformed payload
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <label
        htmlFor={`chip-${fieldId}`}
        className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider px-1"
      >
        {label}
      </label>
      <div
        onClick={() => inputRef.current?.focus()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex flex-wrap items-center gap-1.5 min-h-[38px] px-2.5 py-1.5 rounded-full bg-white/55 border transition-colors cursor-text ${
          dragOver ? "border-accent-500 ring-2 ring-accent-500/30" : "border-slate-200"
        }`}
      >
        {values.map((email, i) => (
          <span
            key={`${email}-${i}`}
            draggable
            onDragStart={(e) => handleDragStart(e, email)}
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-accent-100 text-accent-700 text-[12px] font-medium select-none cursor-grab active:cursor-grabbing"
          >
            <span className="truncate max-w-[180px]">{email}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                removeAt(i);
              }}
              aria-label={`Remove ${email}`}
              className="text-accent-600/70 hover:text-accent-700 text-[13px] leading-none"
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={`chip-${fieldId}`}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKey}
          onBlur={handleBlur}
          placeholder={values.length === 0 ? placeholder : ""}
          className="flex-1 min-w-[120px] bg-transparent outline-none text-[13px] text-slate-900 placeholder:text-slate-400"
        />
      </div>
    </div>
  );
}

export default EmailChipInput;
