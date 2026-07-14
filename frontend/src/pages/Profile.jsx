import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2, UploadCloud } from "lucide-react";
import { useProfile, useUpdateProfile, useImportResume } from "../hooks/useProfile";
import CityMultiSelect from "../components/Profile/CityMultiSelect";

const COMMON_ROLES = [
  "Software Engineer",
  "Frontend Developer",
  "Backend Developer",
  "Full Stack Developer",
  "React Developer",
  "Python Developer",
  "Java Developer",
  "Node.js Developer",
  "AI Engineer",
  "Machine Learning Engineer",
  "Data Analyst",
  "Data Engineer",
  "DevOps Engineer",
  "QA Engineer",
  "SDET",
  "Product Manager",
  "Business Analyst",
  "UI/UX Designer",
];

const EMPTY_FORM = {
  full_name: "",
  phone: "",
  experience_years: "",
  experience_months: "",
  desired_roles: [],
  preferred_locations: [],
  skills: [],
};

function asTags(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (typeof value === "string" && value.trim()) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.filter(Boolean);
    } catch {
      // legacy CSV
    }
    return value.split(",").map((item) => item.trim()).filter(Boolean);
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
  const navigate = useNavigate();
  const { data: profile } = useProfile();
  const { mutateAsync: save, isPending, isSuccess } = useUpdateProfile();
  const { mutateAsync: importResume, isPending: importing } = useImportResume();
  const [form, setForm] = useState(EMPTY_FORM);
  const [roleDraft, setRoleDraft] = useState("");
  const [skillDraft, setSkillDraft] = useState("");
  const [resume, setResume] = useState({ has: false, fileName: null, chars: null, error: null, warning: null });
  const [savedPrompt, setSavedPrompt] = useState(false);
  const [saveError, setSaveError] = useState("");
  const resumeInputRef = useRef(null);
  const seededRef = useRef(false);

  useEffect(() => {
    if (!profile) return;
    if (seededRef.current) {
      if (profile.resume_text) {
        setResume((current) => ({ ...current, has: true, chars: profile.resume_text.length }));
      }
      return;
    }
    seededRef.current = true;
    setForm({
      full_name: profile.full_name || "",
      phone: profile.phone || "",
      experience_years: profile.experience_years ?? "",
      experience_months: profile.experience_months ?? "",
      desired_roles: asTags(profile.desired_roles),
      preferred_locations: asTags(profile.preferred_locations),
      skills: asTags(profile.skills),
    });
    if (profile.resume_text) {
      setResume((current) => ({ ...current, has: true, chars: profile.resume_text.length }));
    }
  }, [profile]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addRole(raw) {
    const parts = String(raw || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!parts.length) return;
    setForm((current) => {
      const next = [...current.desired_roles];
      for (const part of parts) {
        if (!next.some((item) => item.toLowerCase() === part.toLowerCase())) next.push(part);
      }
      return { ...current, desired_roles: next };
    });
    setRoleDraft("");
  }

  function removeRole(role) {
    setForm((current) => ({
      ...current,
      desired_roles: current.desired_roles.filter((item) => item !== role),
    }));
  }

  function addSkill(raw) {
    const parts = String(raw || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!parts.length) return;
    setForm((current) => {
      const next = [...current.skills];
      for (const part of parts) {
        if (!next.some((item) => item.toLowerCase() === part.toLowerCase())) next.push(part);
      }
      return { ...current, skills: next };
    });
    setSkillDraft("");
  }

  function removeSkill(skill) {
    setForm((current) => ({
      ...current,
      skills: current.skills.filter((item) => item !== skill),
    }));
  }

  async function handleResume(file) {
    const name = file?.name?.toLowerCase() || "";
    if (!file || !(name.endsWith(".pdf") || name.endsWith(".docx"))) {
      setResume((current) => ({ ...current, error: "Please choose a PDF or DOCX resume.", warning: null }));
      return;
    }

    setResume({ has: false, fileName: file.name, chars: null, error: null, warning: null });
    try {
      const { draft, warning } = await importResume(file);
      const contact = draft?.contact || {};
      const chars = (draft?.resume_text || "").length;
      setResume({ has: true, fileName: file.name, chars, error: null, warning: warning || null });
      setForm((current) => ({
        ...current,
        full_name: current.full_name || draft?.full_name || contact.full_name || "",
        phone: current.phone || draft?.phone || contact.phone || "",
        skills: current.skills.length ? current.skills : asTags(draft?.skills),
        desired_roles: current.desired_roles.length ? current.desired_roles : asTags(draft?.desired_roles),
      }));
    } catch (error) {
      setResume({
        has: false,
        fileName: null,
        chars: null,
        warning: null,
        error: error?.response?.data?.detail || "Couldn't read that resume. Try a text-based PDF/DOCX.",
      });
    }
  }

  function requiredErrors(nextRoles, nextSkills) {
    const errors = [];
    if (!nextRoles.length) errors.push("Add at least one desired role.");
    if (!form.preferred_locations.length) errors.push("Add at least one desired location.");
    if (form.experience_years === "" && form.experience_months === "") errors.push("Add your total experience.");
    if (!nextSkills.length) errors.push("Add at least one skill.");
    return errors;
  }

  async function submitProfile({ goToJobs = false } = {}) {
    setSaveError("");
    const nextRoles = [...form.desired_roles];
    for (const role of roleDraft.split(",").map((item) => item.trim()).filter(Boolean)) {
      if (!nextRoles.some((item) => item.toLowerCase() === role.toLowerCase())) nextRoles.push(role);
    }
    const nextSkills = [...form.skills];
    for (const skill of skillDraft.split(",").map((item) => item.trim()).filter(Boolean)) {
      if (!nextSkills.some((item) => item.toLowerCase() === skill.toLowerCase())) nextSkills.push(skill);
    }
    const errors = requiredErrors(nextRoles, nextSkills);
    if (errors.length) {
      setSaveError(errors.join(" "));
      return;
    }
    setForm((current) => ({ ...current, desired_roles: nextRoles, skills: nextSkills }));
    setRoleDraft("");
    setSkillDraft("");
    try {
      await save({
        full_name: form.full_name,
        phone: form.phone,
        experience_years: form.experience_years === "" ? null : Number(form.experience_years),
        experience_months: form.experience_months === "" ? null : Number(form.experience_months),
        desired_roles: nextRoles.join(", "),
        preferred_locations: form.preferred_locations,
        skills: nextSkills,
      });
      if (goToJobs) {
        navigate("/jobs?refresh=1");
      } else {
        setSavedPrompt(true);
      }
    } catch (error) {
      setSaveError(error?.response?.data?.detail || "Profile could not be saved. Please check the fields and try again.");
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitProfile();
  }

  const required = [
    resume.has,
    form.desired_roles.length > 0,
    form.preferred_locations.length > 0,
    form.experience_years !== "" || form.experience_months !== "",
    form.skills.length > 0,
  ];
  const done = required.filter(Boolean).length;
  const pct = Math.round((done / 5) * 100);
  const barColor = pct >= 100 ? "bg-success" : pct >= 60 ? "bg-warning" : "bg-danger";

  return (
    <div className="p-6 w-full max-w-3xl mx-auto">
      {savedPrompt && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 px-4">
          <div className="glass-strong w-full max-w-sm rounded-2xl p-5 text-center shadow-2xl animate-fade-in">
            <CheckCircle2 size={34} className="mx-auto text-success mb-3" />
            <h2 className="text-lg font-semibold text-foreground">Profile saved</h2>
            <p className="text-[13px] text-muted-foreground mt-1">
              Your recommendations are ready to refresh from your latest resume, roles, skills, and locations.
            </p>
            <div className="flex items-center justify-center gap-2 mt-5">
              <button type="button" className="btn-secondary" onClick={() => setSavedPrompt(false)}>
                Stay here
              </button>
              <button type="button" className="btn-primary" onClick={() => navigate("/jobs?refresh=1")}>
                Explore Jobs
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="flex items-end justify-between gap-4 mb-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
          <p className="text-[13px] text-muted-foreground mt-0.5">
            Upload your resume, then edit roles, skills, experience, and locations manually.
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
        <Card title="Resume" subtitle="Required. We extract name, phone, skills, and likely job roles. You can edit everything below.">
          <input
            ref={resumeInputRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(event) => { handleResume(event.target.files?.[0]); event.target.value = ""; }}
          />
          <div
            onClick={() => resumeInputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => { event.preventDefault(); handleResume(event.dataTransfer.files?.[0]); }}
            className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer transition-all py-8 px-4 ${
              resume.has ? "border-success/50 bg-success/5" : "border-border hover:border-brand/50 hover:bg-muted/40"
            }`}
          >
            {importing ? (
              <>
                <Loader2 size={26} className="text-brand animate-spin" />
                <p className="text-[12px] text-muted-foreground">Reading your resume...</p>
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
                <p className="text-[13px] font-semibold text-foreground">Click or drag and drop your resume</p>
                <p className="text-[11px] text-muted-foreground">PDF or DOCX · max 10 MB</p>
              </>
            )}
          </div>
          {resume.warning && <p className="text-[12px] text-warning font-medium">{resume.warning}</p>}
          {resume.error && <p className="text-[12px] text-danger font-medium">{resume.error}</p>}
        </Card>

        <Card title="Manual Review" subtitle="Add or correct anything the resume parser missed.">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Full Name">
              <input className="input-glass" value={form.full_name} onChange={(event) => setField("full_name", event.target.value)} placeholder="Aarav Sharma" />
            </Field>
            <Field label="Contact Number">
              <input className="input-glass" type="tel" value={form.phone} onChange={(event) => setField("phone", event.target.value)} placeholder="+91 98765 43210" />
            </Field>
          </div>
        </Card>

        <Card title="Job Preferences" subtitle="Add multiple roles and locations. Location is a hard recommendation filter.">
          <div className="space-y-4">
            <Field label="Desired Roles *">
              <div className="space-y-3">
                <div className="input-glass !h-auto min-h-[46px] !p-2">
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {form.desired_roles.map((role) => (
                      <span key={role} className="pill pill-brand">
                        {role}
                        <button type="button" onClick={() => removeRole(role)} className="ml-1 hover:opacity-60" aria-label={`Remove ${role}`}>
                          x
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <input
                      value={roleDraft}
                      onChange={(event) => setRoleDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === ",") {
                          event.preventDefault();
                          addRole(roleDraft);
                        }
                      }}
                      placeholder={form.desired_roles.length ? "Add another role" : "Add a role (e.g. Software Engineer)"}
                      className="min-h-8 flex-1 bg-transparent text-[13px] text-slate-800 outline-none placeholder:text-slate-400"
                    />
                    <button type="button" onClick={() => addRole(roleDraft)} className="btn-secondary !rounded-lg !px-3 !py-1.5 text-[12px]">
                      Add role
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {COMMON_ROLES.filter((role) => !form.desired_roles.some((item) => item.toLowerCase() === role.toLowerCase()))
                    .slice(0, 12)
                    .map((role) => (
                      <button key={role} type="button" onClick={() => addRole(role)} className="rounded-full border border-border bg-card px-2.5 py-1 text-[11.5px] font-semibold text-muted-foreground hover:border-brand/40 hover:text-brand">
                        {role}
                      </button>
                    ))}
                </div>
              </div>
            </Field>
            <Field label="Desired Locations *">
              <CityMultiSelect value={form.preferred_locations} onChange={(value) => setField("preferred_locations", value)} />
            </Field>
          </div>
        </Card>

        <Card title="Experience *" subtitle="Total professional experience sets the level we match you to.">
          <div className="flex items-end gap-3">
            <Field label="Years">
              <input className="input-glass w-24" type="number" min={0} max={50} value={form.experience_years} onChange={(event) => setField("experience_years", event.target.value)} placeholder="2" />
            </Field>
            <Field label="Months">
              <input className="input-glass w-24" type="number" min={0} max={11} value={form.experience_months} onChange={(event) => setField("experience_months", event.target.value)} placeholder="6" />
            </Field>
          </div>
        </Card>

        <Card title="Skills *" subtitle="Comma or Enter to add. Resume extraction fills this, but manual edits are expected.">
          <div className="input-glass !h-auto min-h-[46px] !p-2">
            <div className="mb-2 flex flex-wrap gap-1.5">
              {form.skills.map((skill) => (
                <span key={skill} className="pill border border-accent-200/60 bg-accent-100/80 text-accent-700">
                  {skill}
                  <button type="button" onClick={() => removeSkill(skill)} className="ml-1 text-slate-400 hover:text-rose-500" aria-label={`Remove ${skill}`}>
                    x
                  </button>
                </span>
              ))}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={skillDraft}
                onChange={(event) => setSkillDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === ",") {
                    event.preventDefault();
                    addSkill(skillDraft);
                  }
                }}
                placeholder={form.skills.length ? "Add another skill" : "Add a skill (e.g. React, Python, AWS)"}
                className="min-h-8 flex-1 bg-transparent text-[13px] text-slate-800 outline-none placeholder:text-slate-400"
              />
              <button type="button" onClick={() => addSkill(skillDraft)} className="btn-secondary !rounded-lg !px-3 !py-1.5 text-[12px]">
                Add skill
              </button>
            </div>
          </div>
        </Card>

        {saveError && (
          <div className="rounded-2xl border border-danger/25 bg-danger/10 px-4 py-3 text-[13px] font-medium text-danger">
            {saveError}
          </div>
        )}

        <div className="sticky bottom-3 z-20 flex flex-col gap-3 rounded-2xl border border-border bg-card/95 p-3 shadow-[0_18px_50px_-32px_rgba(15,23,42,0.35)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[12px] text-muted-foreground">
            Desired roles, locations, experience, and skills are required for useful job matches.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <button type="submit" disabled={isPending} className="btn-secondary">
            {isPending ? "Saving..." : "Save Profile"}
            </button>
            <button type="button" disabled={isPending} onClick={() => submitProfile({ goToJobs: true })} className="btn-primary">
              {isPending ? "Saving..." : "Save and View Jobs"}
            </button>
            {isSuccess && (
              <span className="inline-flex items-center gap-1.5 text-[13px] text-success font-semibold animate-fade-in">
                <CheckCircle2 size={16} /> Saved
              </span>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
