import { useState } from "react";
import { X } from "lucide-react";
import { emailApi } from "../../services/api";

const PURPOSES = ["General", "Job Alerts", "Interviews", "Assessments", "Rejections"];

// userLabels: [{id, name}] used for the "nest under" parent options.
export default function NewLabelDialog({ userLabels = [], onClose, onCreated }) {
  const [name, setName] = useState("");
  const [nestUnder, setNestUnder] = useState("");
  const [purpose, setPurpose] = useState("General");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function create() {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      // nest_under is the parent label NAME (Gmail nests via "Parent/Child").
      await emailApi.createLabel({ name: name.trim(), nest_under: nestUnder || null, purpose });
      onCreated();
    } catch (e) {
      setError(e?.response?.data?.detail || "Couldn't create the label.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="glass-strong rounded-2xl p-5 w-full max-w-sm">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold">New label</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Label name</label>
            <input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Startups" className="input-glass" />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Nest under</label>
            <select value={nestUnder} onChange={(e) => setNestUnder(e.target.value)} className="input-glass">
              <option value="">None</option>
              {userLabels.map((l) => <option key={l.id} value={l.name}>{l.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Purpose</label>
            <select value={purpose} onChange={(e) => setPurpose(e.target.value)} className="input-glass">
              {PURPOSES.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          {error && <p className="text-[12px] text-danger">{error}</p>}
        </div>

        <div className="flex gap-2 mt-4">
          <button onClick={onClose} className="btn-secondary flex-1 text-[13px]">Cancel</button>
          <button onClick={create} disabled={saving || !name.trim()} className="btn-primary flex-1 text-[13px]">
            {saving ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
