import { useEffect, useRef, useState } from "react";
import { CheckCircle2, FileText, Loader2, UploadCloud } from "lucide-react";
import { useProfile, useUpdateProfile, useImportResume } from "../hooks/useProfile";
import TagInput from "../components/Profile/TagInput";
import CityMultiSelect from "../components/Profile/CityMultiSelect";

const LINK_FIELDS = [
  { key: "linkedin_url", label: "LinkedIn",  placeholder: "https://linkedin.com/in/…" },
  { key: "github_url",   label: "GitHub",    placeholder: "https://github.com/…" },
  { key: "website_url",  label: "Portfolio", placeholder: "https://yoursite.com" },
];

const EMPTY_FORM = {
  full_name: "", phone: "",
  experience_years: "", experience_months: "",
  preferred_locations: [], skills: [],
  linkedin_url: "", github_url: "", website_url: "",
};

function asTags(v) {
  if (Array.isArray(v)) return v.filter(Boolean);
  if (typeof v === "string" && v.trim()) {
    try { const p = JSON.parse(v); if (Array.isArray(p)) return p.filter(Boolean); } catch { /* csv */ }
    return v.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

function Card({ title, subtitle, children }) {
  return (
    <section className="glass-subtle rounded-2xl p-5 space-y-4">
      <div>
        <h2 className="text-[14px] font-semibold text-foreground tracking-tight">{title}</h2>
        {subtitle && <p className="text-[12px] text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">{label}</label>
      {children}
    </div>
  );
}

export default function Profile() {
  const { data: profile } = useProfile();
  const { mutate: save, isPending, isSuccess } = useUpdateProfile();
  const { mutateAsync: importResume, isPending: importing } = useImportResume();

  const [form, setForm] = useState(EMPTY_FORM);
  const [resume, setResume] = useState({ has: false, fileName: null, chars: null, error: null });
  const resumeInputRef = useRef(null);
  const seededRef = useRef(false);

  // Seed the form once from the API (not on every refetch, so an in-flight save
  // never clobbers edits).
  useEffect(() => {
    if (!profile || seededRef.current) return;
    seededRef.current = true;
    setForm({
      full_name: profile.full_name || "",
      phone: profile.phone || "",
      experience_years: profile.experience_years ?? "",
      experience_months: profile.experience_months ?? "",
      preferred_locations: asTags(profile.preferred_locations),
      skills: asTags(profile.skills),
      linkedin_url: profile.linkedin_url || "",
      github_url: profile.github_url || "",
      website_url: profile.website_url || "",
    });
    if (profile.resume_text) {
      setResume((s) => ({ ...s, has: true, chars: profile.resume_text.length }));
    }
  }, [profile]);

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  // Resume drop → parse (also persists resume_text server-side) → autofill blanks.
  async function handleResume(file) {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
      setResume((s) => ({ ...s, error: "Please choose a PDF resume." }));
      return;
    }
    setResume({ has: false, fileName: file.name, chars: null, error: null });
    try {
      const { draft } = await importResume(file);
      setResume({ has: true, fileName: file.name, chars: (draft?.resume_text || "").length, error: null });
      setForm((prev) => ({
        ...prev,
        full_name: prev.full_name || draft?.full_name || "",
        phone: prev.phone || draft?.phone || "",
        skills: prev.skills.length ? prev.skills : asTags(draft?.skills),
      }));
    } catch (err) {
      setResume({ has: false, fileName: null, chars: null, error: err?.response?.data?.detail || "Couldn't read that PDF." });
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    save({
      full_name: form.full_name,
      phone: form.phone,
      experience_years: form.experience_years === "" ? null : Number(form.experience_years),
      experience_months: form.experience_months === "" ? null : Number(form.experience_months),
      preferred_locations: form.preferred_locations,
      skills: form.skills,
      linkedin_url: form.linkedin_url,
      github_url: form.github_url,
      website_url: form.website_url,
    });
  }

  // 5 required fields drive the completion gate shared with /jobs.
  const required = [
    !!form.full_name.trim(),
    !!form.phone.trim(),
    form.experience_years !== "" || form.experience_months !== "",
    form.preferred_locations.length > 0,
    resume.has,
  ];
  const done = required.filter(Boolean).length;
  const pct = Math.round((done / 5) * 100);
  const barColor = pct >= 100 ? "bg-success" : pct >= 60 ? "bg-warning" : "bg-danger";

  return (
    <div className="p-6 w-full max-w-3xl mx-auto">
      {/* Header + completion */}
      <div className="flex items-end justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            The essentials we need to find the right jobs for you.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-28 h-1.5 bg-muted rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
          </div>
          <span className="text-[12px] text-muted-foreground font-semibold tnum">{done}/5</span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Resume — required, also autofills name/phone/skills */}
        <Card title="Resume" subtitle="Required — used to match you to jobs. We'll autofill what we can.">
          <input ref={resumeInputRef} type="file" accept=".pdf" className="hidden"
                 onChange={(e) => { handleResume(e.target.files?.[0]); e.target.value = ""; }} />
          <div
            onClick={() => resumeInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); handleResume(e.dataTransfer.files?.[0]); }}
            className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer transition-all py-8 px-4 ${
              resume.has ? "border-success/50 bg-success/5" : "border-border hover:border-brand/50 hover:bg-muted/40"
            }`}
          >
            {importing ? (
              <>
                <Loader2 size={26} className="text-brand animate-spin" />
                <p className="text-[12px] text-muted-foreground">Reading your resume…</p>
              </>
            ) : resume.has ? (
              <>
                <CheckCircle2 size={26} className="text-success" />
                {resume.fileName && <p className="text-[13px] font-semibold text-foreground">{resume.fileName}</p>}
                <p className="text-[12px] text-success font-medium">
                  Resume loaded{resume.chars ? ` · ${resume.chars.toLocaleString()} characters` : ""}
                </p>
                <p className="text-[11px] text-muted-foreground mt-0.5">Click or drop to replace</p>
              </>
            ) : (
              <>
                <UploadCloud size={26} className="text-muted-foreground" />
                <p className="text-[13px] font-semibold text-foreground">Click or drag &amp; drop your resume PDF</p>
                <p className="text-[11px] text-muted-foreground">PDF only · max 10 MB</p>
              </>
            )}
          </div>
          {resume.error && <p className="text-[12px] text-danger font-medium">{resume.error}</p>}
        </Card>

        {/* Basics */}
        <Card title="Basics" subtitle="Name and contact, exactly as they should appear on applications.">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Full Name *">
              <input className="input-glass" value={form.full_name}
                     onChange={(e) => setField("full_name", e.target.value)} placeholder="Aarav Sharma" />
            </Field>
            <Field label="Contact Number *">
              <input className="input-glass" type="tel" value={form.phone}
                     onChange={(e) => setField("phone", e.target.value)} placeholder="+91 98765 43210" />
            </Field>
          </div>
        </Card>

        {/* Experience — drives entry/mid/senior targeting */}
        <Card title="Experience *" subtitle="Total professional experience — sets the level we match you to (entry / mid / senior).">
          <div className="flex items-end gap-3">
            <Field label="Years">
              <input className="input-glass w-24" type="number" min={0} max={50} value={form.experience_years}
                     onChange={(e) => setField("experience_years", e.target.value)} placeholder="2" />
            </Field>
            <Field label="Months">
              <input className="input-glass w-24" type="number" min={0} max={11} value={form.experience_months}
                     onChange={(e) => setField("experience_months", e.target.value)} placeholder="6" />
            </Field>
          </div>
        </Card>

        {/* Preferred locations */}
        <Card title="Preferred Locations *" subtitle="Where you want to work — pick any number of cities (or Remote).">
          <CityMultiSelect value={form.preferred_locations} onChange={(v) => setField("preferred_locations", v)} />
        </Card>

        {/* Skills */}
        <Card title="Skills" subtitle="Comma or Enter to add — these drive job match scoring.">
          <TagInput value={form.skills} onChange={(v) => setField("skills", v)} placeholder="Add a skill (e.g. React, Python, AWS)" />
        </Card>

        {/* Links */}
        <Card title="Links" subtitle="Optional — your professional links.">
          <div className="space-y-4">
            {LINK_FIELDS.map(({ key, label, placeholder }) => (
              <Field key={key} label={label}>
                <input className="input-glass" type="url" value={form[key]}
                       onChange={(e) => setField(key, e.target.value)} placeholder={placeholder} />
              </Field>
            ))}
          </div>
        </Card>

        <div className="flex items-center gap-4 pb-8 pt-1">
          <button type="submit" disabled={isPending} className="btn-primary">
            {isPending ? "Saving…" : "Save Profile"}
          </button>
          {isSuccess && (
            <span className="inline-flex items-center gap-1.5 text-[13px] text-success font-semibold animate-fade-in">
              <CheckCircle2 size={16} /> Saved
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
