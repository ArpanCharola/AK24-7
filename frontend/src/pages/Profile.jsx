import { useEffect, useRef, useState } from "react";
import { useProfile, useUpdateProfile, useImportResume } from "../hooks/useProfile";
import { useEmailStatus, useConnectEmail, useDisconnectEmail, useScanEmail } from "../hooks/useEmail";
import { profileApi } from "../services/api";
import TagInput from "../components/Profile/TagInput";
import RepeatableSection from "../components/Profile/RepeatableSection";

const PERSONAL_FIELDS = [
  { key: "full_name", label: "Full Name", type: "text", placeholder: "Aarav Sharma" },
  { key: "phone",     label: "Phone",     type: "tel",  placeholder: "+91 98765 43210" },
  { key: "location",  label: "Current Location", type: "text", placeholder: "Bengaluru, India" },
];

const LINK_FIELDS = [
  { key: "linkedin_url", label: "LinkedIn", type: "url", placeholder: "https://linkedin.com/in/…" },
  { key: "github_url",   label: "GitHub",   type: "url", placeholder: "https://github.com/…" },
  { key: "website_url",  label: "Portfolio", type: "url", placeholder: "https://yoursite.com" },
];

const WORK_FIELDS = [
  { key: "title", label: "Role / Title", placeholder: "Senior Software Engineer" },
  { key: "company", label: "Company", placeholder: "Swiggy" },
  { key: "location", label: "Location", placeholder: "Bengaluru" },
  { key: "start_date", label: "Start", placeholder: "Jan 2022" },
  { key: "end_date", label: "End", placeholder: "Present" },
  { key: "description", label: "Highlights", placeholder: "Impact, scope, tech…", textarea: true, full: true },
];

const EDU_FIELDS = [
  { key: "degree", label: "Degree", placeholder: "B.Tech" },
  { key: "field", label: "Field", placeholder: "Computer Science" },
  { key: "institution", label: "Institution", placeholder: "IIT Bombay", full: true },
  { key: "start_date", label: "Start", placeholder: "2018" },
  { key: "end_date", label: "End", placeholder: "2022" },
  { key: "grade", label: "Grade / CGPA", placeholder: "8.6 CGPA" },
];

const PROJECT_FIELDS = [
  { key: "name", label: "Project", placeholder: "Realtime analytics pipeline" },
  { key: "link", label: "Link", type: "url", placeholder: "https://github.com/…" },
  { key: "description", label: "Description", placeholder: "What it does, your role, tech…", textarea: true, full: true },
];

const CERT_FIELDS = [
  { key: "name", label: "Certification", placeholder: "AWS Solutions Architect" },
  { key: "issuer", label: "Issuer", placeholder: "Amazon Web Services" },
  { key: "year", label: "Year", placeholder: "2024" },
];

function asArray(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === "string" && v.trim()) {
    try { const p = JSON.parse(v); return Array.isArray(p) ? p : []; } catch { return []; }
  }
  return [];
}

function asTags(v) {
  if (Array.isArray(v)) return v.filter(Boolean);
  if (typeof v === "string" && v.trim()) {
    try { const p = JSON.parse(v); if (Array.isArray(p)) return p.filter(Boolean); } catch { /* not json */ }
    return v.split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

function SectionCard({ icon, title, subtitle, action, children }) {
  return (
    <section className="glass-subtle rounded-2xl overflow-hidden">
      <div className="px-6 py-4 border-b border-white/40 flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "hsl(var(--muted))" }}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-[14px] font-semibold text-slate-900 tracking-tight">{title}</h2>
          {subtitle && <p className="text-[11.5px] text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="p-6 space-y-4">{children}</div>
    </section>
  );
}

const EMPTY_FORM = {
  full_name: "", phone: "", location: "",
  linkedin_url: "", github_url: "", website_url: "",
  summary: "",
  current_ctc_lpa: "", expected_ctc_lpa: "", notice_period: "", work_authorization: "",
  preferred_locations: [],
  skills: [],
  work_experience: [],
  education: [],
  projects: [],
  certifications: [],
};

export default function Profile() {
  const { data: profile } = useProfile();
  const { mutate: save, isPending, isSuccess } = useUpdateProfile();
  const { mutateAsync: importResume, isPending: importing } = useImportResume();

  const [form, setForm] = useState(EMPTY_FORM);
  const [resumeState, setResumeState] = useState({ uploading: false, fileName: null, charCount: null, error: null });
  const [importBanner, setImportBanner] = useState(null);
  const importInputRef = useRef(null);
  const resumeInputRef = useRef(null);
  const seededRef = useRef(false);

  // Seed the form ONCE from the profile. We don't re-seed on every refetch so a
  // save that the (in-progress) backend doesn't yet round-trip won't wipe edits.
  useEffect(() => {
    if (!profile || seededRef.current) return;
    seededRef.current = true;
    setForm({
      full_name: profile.full_name || "",
      phone: profile.phone || "",
      location: profile.location || "",
      linkedin_url: profile.linkedin_url || "",
      github_url: profile.github_url || "",
      website_url: profile.website_url || "",
      summary: profile.summary || "",
      current_ctc_lpa: profile.current_ctc_lpa ?? "",
      expected_ctc_lpa: profile.expected_ctc_lpa ?? "",
      notice_period: profile.notice_period || "",
      work_authorization: profile.work_authorization || "",
      preferred_locations: asTags(profile.preferred_locations),
      skills: asTags(profile.skills),
      work_experience: asArray(profile.work_experience),
      education: asArray(profile.education),
      projects: asArray(profile.projects),
      certifications: asArray(profile.certifications),
    });
    if (profile.resume_text) {
      setResumeState((s) => ({ ...s, charCount: profile.resume_text.length }));
    }
  }, [profile]);

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleChange(e) {
    setField(e.target.name, e.target.value);
  }

  function handleSubmit(e) {
    e.preventDefault();
    save(form);
  }

  // ── Import from resume (parse → review → save) ──────────────────────────────
  async function handleImportFile(file) {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
      setImportBanner({ type: "error", msg: "Please choose a PDF resume." });
      return;
    }
    setImportBanner(null);
    try {
      const parsed = await importResume(file);
      setForm((prev) => ({
        ...prev,
        full_name: parsed.full_name || prev.full_name,
        phone: parsed.phone || prev.phone,
        location: parsed.location || prev.location,
        linkedin_url: parsed.linkedin_url || prev.linkedin_url,
        github_url: parsed.github_url || prev.github_url,
        website_url: parsed.website_url || prev.website_url,
        summary: parsed.summary || prev.summary,
        skills: asTags(parsed.skills).length ? asTags(parsed.skills) : prev.skills,
        work_experience: asArray(parsed.work_experience).length ? asArray(parsed.work_experience) : prev.work_experience,
        education: asArray(parsed.education).length ? asArray(parsed.education) : prev.education,
        projects: asArray(parsed.projects).length ? asArray(parsed.projects) : prev.projects,
        certifications: asArray(parsed.certifications).length ? asArray(parsed.certifications) : prev.certifications,
      }));
      if (parsed.resume_text) setResumeState((s) => ({ ...s, charCount: parsed.resume_text.length }));
      setImportBanner({ type: "success", msg: "Parsed your resume — review the fields below, then Save." });
    } catch (err) {
      const offline = err?.response?.status === 404;
      setImportBanner({
        type: "error",
        msg: offline
          ? "Resume import isn't available yet — you can still fill sections manually or upload a base resume below."
          : err?.response?.data?.detail || "Couldn't parse the resume.",
      });
    }
  }

  // ── Base resume (raw text) upload — feeds resume tailoring ──────────────────
  async function handleResumePdf(file) {
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) {
      setResumeState((s) => ({ ...s, error: "Please select a PDF file" }));
      return;
    }
    setResumeState({ uploading: true, fileName: file.name, charCount: null, error: null });
    try {
      const res = await profileApi.uploadResume(file);
      setResumeState({ uploading: false, fileName: file.name, charCount: res.data.char_count, error: null });
    } catch (err) {
      setResumeState({ uploading: false, fileName: null, charCount: null, error: err?.response?.data?.detail || "Failed to parse PDF" });
    }
  }

  // ── Gmail connection ────────────────────────────────────────────────────────
  const { data: emailStatus } = useEmailStatus();
  const { mutate: connectEmail, isPending: connecting } = useConnectEmail();
  const { mutate: disconnectEmail } = useDisconnectEmail();
  const { mutate: scanEmail, isPending: scanning, data: scanResult } = useScanEmail();
  const [gmailBanner, setGmailBanner] = useState(null);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("gmail");
    if (!p) return;
    const map = {
      connected: { type: "success", msg: "Gmail connected — we'll track application replies and interview invites." },
      denied: { type: "error", msg: "Gmail connection was cancelled." },
      error: { type: "error", msg: "Couldn't connect Gmail. Check the Google OAuth setup." },
    };
    if (map[p]) setGmailBanner(map[p]);
    window.history.replaceState({}, "", window.location.pathname);
  }, []);

  function handleConnectGmail() {
    connectEmail(undefined, {
      onSuccess: (url) => { window.location.href = url; },
      onError: (e) => setGmailBanner({ type: "error", msg: e?.response?.data?.detail || "Google OAuth is not configured." }),
    });
  }

  const hasResume = resumeState.charCount !== null;
  const filled = [
    form.full_name, form.phone, form.location, form.linkedin_url, hasResume,
    form.skills.length > 0, form.work_experience.length > 0,
  ].filter(Boolean).length;
  const pct = Math.round((filled / 7) * 100);
  const pctGradient = pct >= 80 ? "from-emerald-400 to-emerald-500" : pct >= 50 ? "from-amber-400 to-amber-500" : "from-rose-400 to-rose-500";

  const accentIcon = (d) => (
    <svg className="w-[18px] h-[18px] text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      {/* Header */}
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Profile</h1>
            <p className="text-[13px] text-slate-500 mt-0.5">Drives your job matches, why-fit scoring and tailored resumes</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-28 h-1.5 bg-slate-200/60 rounded-full overflow-hidden">
              <div className={`h-full rounded-full bg-gradient-to-r ${pctGradient} transition-all`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[12px] text-slate-600 font-semibold">{pct}% complete</span>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-6">
          <form onSubmit={handleSubmit} className="space-y-5">

            {/* Import from resume */}
            <SectionCard
              icon={accentIcon("M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12")}
              title="Import from resume"
              subtitle="Upload a PDF — we parse it into the sections below for you to review & edit"
            >
              <input ref={importInputRef} type="file" accept=".pdf" className="hidden"
                     onChange={(e) => { handleImportFile(e.target.files?.[0]); e.target.value = ""; }} />
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-[12.5px] text-slate-500 max-w-sm">
                  Fastest way to build your profile — autofill name, experience, education, skills, projects & certifications.
                </p>
                <button type="button" onClick={() => importInputRef.current?.click()} disabled={importing} className="btn-primary text-[13px]">
                  {importing ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                        <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                      </svg>
                      Parsing…
                    </>
                  ) : "Upload & parse resume"}
                </button>
              </div>
              {importBanner && (
                <div className={`px-3 py-2 rounded-xl text-[12.5px] ${importBanner.type === "success" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-600"}`}>
                  {importBanner.msg}
                </div>
              )}
            </SectionCard>

            {/* Personal Info */}
            <SectionCard icon={accentIcon("M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z")} title="Personal Info">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {PERSONAL_FIELDS.map(({ key, label, type, placeholder }) => (
                  <div key={key}>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">{label}</label>
                    <input type={type} name={key} value={form[key]} onChange={handleChange} placeholder={placeholder} className="input-glass" />
                  </div>
                ))}
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Professional Summary</label>
                <textarea name="summary" value={form.summary} onChange={handleChange} rows={3}
                  placeholder="A 2–3 line headline of who you are and what you do."
                  className="w-full text-[13px] px-3 py-2 bg-white/55 rounded-lg border border-slate-200/60 text-slate-800 outline-none focus:ring-2 focus:ring-accent-300/60 resize-y" />
              </div>
            </SectionCard>

            {/* India career details */}
            <SectionCard
              icon={accentIcon("M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z")}
              title="Career Details"
              subtitle="Salary in LPA & notice period — used to rank and filter your matches"
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Current CTC (LPA)</label>
                  <input type="number" min={0} step="0.1" name="current_ctc_lpa" value={form.current_ctc_lpa} onChange={handleChange} placeholder="12" className="input-glass" />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Expected CTC (LPA)</label>
                  <input type="number" min={0} step="0.1" name="expected_ctc_lpa" value={form.expected_ctc_lpa} onChange={handleChange} placeholder="18" className="input-glass" />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Notice Period</label>
                  <input type="text" name="notice_period" value={form.notice_period} onChange={handleChange} placeholder="30 days / Immediate" className="input-glass" />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Work Authorization</label>
                  <input type="text" name="work_authorization" value={form.work_authorization} onChange={handleChange} placeholder="Indian citizen" className="input-glass" />
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">Preferred Locations</label>
                <TagInput value={form.preferred_locations} onChange={(v) => setField("preferred_locations", v)} placeholder="Add a city and press Enter (e.g. Bengaluru)" />
              </div>
            </SectionCard>

            {/* Skills */}
            <SectionCard icon={accentIcon("M13 10V3L4 14h7v7l9-11h-7z")} title="Skills" subtitle="Comma or Enter to add — these drive skill-gap analysis">
              <TagInput value={form.skills} onChange={(v) => setField("skills", v)} placeholder="Add a skill (e.g. React, Python, AWS)" />
            </SectionCard>

            {/* Work Experience */}
            <SectionCard icon={accentIcon("M20 7H4a2 2 0 00-2 2v9a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2zM8 7V5a2 2 0 012-2h4a2 2 0 012 2v2")} title="Work Experience">
              <RepeatableSection items={form.work_experience} onChange={(v) => setField("work_experience", v)} fields={WORK_FIELDS}
                addLabel="Add experience" emptyHint="No experience added yet." titleKey="title" />
            </SectionCard>

            {/* Education */}
            <SectionCard icon={accentIcon("M12 14l9-5-9-5-9 5 9 5z M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z")} title="Education">
              <RepeatableSection items={form.education} onChange={(v) => setField("education", v)} fields={EDU_FIELDS}
                addLabel="Add education" emptyHint="No education added yet." titleKey="degree" />
            </SectionCard>

            {/* Projects */}
            <SectionCard icon={accentIcon("M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4")} title="Projects">
              <RepeatableSection items={form.projects} onChange={(v) => setField("projects", v)} fields={PROJECT_FIELDS}
                addLabel="Add project" emptyHint="No projects added yet." titleKey="name" />
            </SectionCard>

            {/* Certifications */}
            <SectionCard icon={accentIcon("M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z")} title="Certifications">
              <RepeatableSection items={form.certifications} onChange={(v) => setField("certifications", v)} fields={CERT_FIELDS}
                addLabel="Add certification" emptyHint="No certifications added yet." titleKey="name" />
            </SectionCard>

            {/* Professional Links */}
            <SectionCard icon={accentIcon("M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 11-5.656-5.656l1.5-1.5m6.656-2.828l1.5-1.5a4 4 0 115.656 5.656l-3 3a4 4 0 01-5.656 0")} title="Professional Links">
              <div className="space-y-4">
                {LINK_FIELDS.map(({ key, label, type, placeholder }) => (
                  <div key={key}>
                    <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">{label}</label>
                    <input type={type} name={key} value={form[key]} onChange={handleChange} placeholder={placeholder} className="input-glass" />
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Base resume (raw text) */}
            <SectionCard
              icon={accentIcon("M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z")}
              title="Base Resume"
              subtitle="The text used as the starting point for tailored resumes"
            >
              <input ref={resumeInputRef} type="file" accept=".pdf" className="hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) handleResumePdf(f); e.target.value = ""; }} />
              <div
                onClick={() => resumeInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); handleResumePdf(e.dataTransfer.files?.[0]); }}
                className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer transition-all py-8 px-4 ${
                  hasResume ? "border-emerald-300 bg-emerald-50/30 hover:border-emerald-400" : "border-slate-200 hover:border-accent-400 hover:bg-white/40"
                }`}
              >
                {resumeState.uploading ? (
                  <>
                    <svg className="w-6 h-6 text-accent-500 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                    </svg>
                    <p className="text-[12px] text-slate-500">Extracting text…</p>
                  </>
                ) : hasResume ? (
                  <>
                    <svg className="w-7 h-7 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {resumeState.fileName && <p className="text-[13px] font-semibold text-slate-700">{resumeState.fileName}</p>}
                    <p className="text-[12px] text-emerald-600 font-medium">Resume loaded · {resumeState.charCount?.toLocaleString()} characters</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">Click or drop to replace</p>
                  </>
                ) : (
                  <>
                    <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    <p className="text-[13px] font-semibold text-slate-700">Click or drag & drop your resume PDF</p>
                    <p className="text-[11px] text-slate-400">PDF only · max 10 MB</p>
                  </>
                )}
              </div>
              {resumeState.error && <p className="text-[12px] text-rose-500 font-medium">{resumeState.error}</p>}
            </SectionCard>

            {/* Connect Gmail */}
            <SectionCard
              icon={accentIcon("M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z")}
              title="Connect Gmail"
              subtitle="Read-only — track application replies & interview invites (optional)"
            >
              {gmailBanner && (
                <div className={`px-3 py-2 rounded-xl text-[12.5px] mb-1 ${gmailBanner.type === "success" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-600"}`}>
                  {gmailBanner.msg}
                </div>
              )}
              {emailStatus?.connected ? (
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="text-[13px] text-slate-700">
                    <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-600">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Connected
                    </span>
                    <span className="text-slate-500"> · {emailStatus.gmail_email}</span>
                    {scanResult && (
                      <span className="block text-[11.5px] text-slate-400 mt-1">
                        Last scan: {scanResult.scanned} mail · {scanResult.updated} application(s) updated
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => scanEmail()} disabled={scanning} className="btn-secondary !py-1.5 !px-3 text-[12px]">
                      {scanning ? "Scanning…" : "Scan now"}
                    </button>
                    <button type="button" onClick={() => disconnectEmail()} className="text-[12px] font-semibold text-rose-600 hover:text-rose-700 px-2">Disconnect</button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <p className="text-[12.5px] text-slate-500 max-w-sm">
                    Lets AK24/7Jobs detect application confirmations and advance status as assessment/interview emails arrive.
                  </p>
                  <button type="button" onClick={handleConnectGmail} disabled={connecting} className="btn-secondary !py-2 !px-4 text-[13px] inline-flex items-center gap-2">
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 11v2.4h5.6c-.24 1.5-1.7 4.4-5.6 4.4-3.37 0-6.12-2.79-6.12-6.2S8.63 5.4 12 5.4c1.92 0 3.2.82 3.94 1.52l2.68-2.58C16.96 2.7 14.7 1.8 12 1.8 6.9 1.8 2.76 5.94 2.76 11s4.14 9.2 9.24 9.2c5.34 0 8.88-3.75 8.88-9.04 0-.6-.07-1.06-.16-1.52H12z" /></svg>
                    {connecting ? "Opening…" : "Connect Gmail"}
                  </button>
                </div>
              )}
              {emailStatus && emailStatus.oauth_configured === false && (
                <p className="text-[11.5px] text-amber-600">Google OAuth isn't configured on the server yet (set GOOGLE_CLIENT_ID / SECRET in the backend .env).</p>
              )}
            </SectionCard>

            <div className="flex items-center gap-4 pb-8 pt-2">
              <button type="submit" disabled={isPending} className="btn-primary">
                {isPending ? "Saving…" : "Save Profile"}
              </button>
              {isSuccess && (
                <span className="inline-flex items-center gap-1.5 text-[13px] text-emerald-600 font-semibold animate-fade-in">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  Saved
                </span>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
