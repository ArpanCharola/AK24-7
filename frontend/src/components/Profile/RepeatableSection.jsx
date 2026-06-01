// Generic editor for a list of structured records (work experience, education,
// projects, certifications). `fields` describes each editable field; `items` is
// the current array; `onChange` receives the updated array.
export default function RepeatableSection({ items = [], onChange, fields, addLabel, emptyHint, titleKey }) {
  function update(idx, key, val) {
    onChange(items.map((it, i) => (i === idx ? { ...it, [key]: val } : it)));
  }
  function add() {
    onChange([...items, Object.fromEntries(fields.map((f) => [f.key, ""]))]);
  }
  function remove(idx) {
    onChange(items.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-3">
      {items.length === 0 && (
        <p className="text-[12px] text-slate-400">{emptyHint}</p>
      )}
      {items.map((item, idx) => (
        <div key={idx} className="rounded-xl border border-slate-200/60 bg-white/40 p-4 space-y-3 relative">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              {(titleKey && item[titleKey]) || `Entry ${idx + 1}`}
            </span>
            <button
              type="button"
              onClick={() => remove(idx)}
              className="p-1 text-slate-300 hover:text-rose-500 rounded-lg hover:bg-rose-50/70 transition-colors"
              title="Remove"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a1 1 0 00-1-1h-4a1 1 0 00-1 1H5" />
              </svg>
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {fields.map((f) => (
              <div key={f.key} className={f.full ? "sm:col-span-2" : ""}>
                <label className="block text-[10.5px] font-semibold text-slate-500 uppercase tracking-wider mb-1">{f.label}</label>
                {f.textarea ? (
                  <textarea
                    rows={3}
                    value={item[f.key] || ""}
                    onChange={(e) => update(idx, f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="w-full text-[12.5px] px-3 py-2 bg-white/60 rounded-lg border border-slate-200/60 text-slate-800 outline-none focus:ring-2 focus:ring-accent-300/60 resize-y"
                  />
                ) : (
                  <input
                    type={f.type || "text"}
                    value={item[f.key] || ""}
                    onChange={(e) => update(idx, f.key, e.target.value)}
                    placeholder={f.placeholder}
                    className="input-glass !py-1.5 text-[12.5px]"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="btn-secondary !py-1.5 !px-3 text-[12px]"
      >
        <svg className="w-3.5 h-3.5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
        {addLabel}
      </button>
    </div>
  );
}
