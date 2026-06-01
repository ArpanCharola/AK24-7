import { useEffect, useMemo, useRef, useState } from "react";
import {
  useTailoredResumes,
  useTailoredResume,
  useUpdateTailoredResume,
  useRetailorResume,
  useRegeneratePdf,
  useQuickTailor,
  useExtractJd,
  useDeleteTailoredResume,
} from "../hooks/useTailoredResumes";
import { tailoredResumesApi, profileApi } from "../services/api";
import { useProfile } from "../hooks/useProfile";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function StatBadge({ value, label, tone }) {
  const tones = {
    add:    "bg-emerald-100/80 text-emerald-700 border-emerald-200/60",
    remove: "bg-rose-100/80 text-rose-700 border-rose-200/60",
    keep:   "bg-slate-100/80 text-slate-600 border-slate-200/60",
    info:   "bg-accent-100/80 text-accent-700 border-accent-200/60",
  };
  return (
    <div className={`pill border ${tones[tone] || tones.info}`}>
      <span className="font-bold">{value}</span>
      <span className="opacity-80">{label}</span>
    </div>
  );
}

function AtsBadge({ score }) {
  if (score == null || score === "") return null;
  const n = Math.round(Number(score));
  if (Number.isNaN(n)) return null;
  const [bg, text, border] =
    n >= 80 ? ["bg-emerald-100/80", "text-emerald-700", "border-emerald-200/60"] :
    n >= 60 ? ["bg-amber-100/80", "text-amber-700", "border-amber-200/60"] :
              ["bg-rose-100/80", "text-rose-700", "border-rose-200/60"];
  return (
    <div className={`pill border ${bg} ${text} ${border}`} title="ATS keyword coverage score">
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span className="font-bold">{n}</span>
      <span className="opacity-80">ATS score</span>
    </div>
  );
}

function DiffView({ segments }) {
  if (!segments?.length) {
    return (
      <div className="text-center py-12 text-[12.5px] text-slate-400">
        No diff to show — tailored resume is identical to the original.
      </div>
    );
  }
  return (
    <div className="font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words rounded-2xl overflow-hidden border border-slate-200/60">
      {segments.map((seg, i) => {
        if (seg.type === "equal") {
          return (
            <div key={i} className="px-4 py-1.5 bg-white/30 text-slate-600">
              {seg.text || " "}
            </div>
          );
        }
        if (seg.type === "insert") {
          return (
            <div key={i} className="px-4 py-1.5 bg-emerald-50/80 border-l-2 border-emerald-400">
              <span className="text-emerald-600 mr-2 font-bold select-none">+</span>
              <span className="text-emerald-900">{seg.text || " "}</span>
            </div>
          );
        }
        if (seg.type === "delete") {
          return (
            <div key={i} className="px-4 py-1.5 bg-rose-50/80 border-l-2 border-rose-400">
              <span className="text-rose-600 mr-2 font-bold select-none">−</span>
              <span className="text-rose-900 line-through opacity-80">{seg.text || " "}</span>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
}

function FullTextView({ text, emptyLabel }) {
  if (!text?.trim()) {
    return (
      <div className="text-center py-12 text-[12.5px] text-slate-400">
        {emptyLabel}
      </div>
    );
  }
  return (
    <div className="font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words px-4 py-3 bg-white/30 rounded-2xl border border-slate-200/60 text-slate-700">
      {text}
    </div>
  );
}

function EditableTailoredView({ value, dirty, onChange, emptyLabel }) {
  return (
    <div className="space-y-2">
      {dirty && (
        <p className="text-[11.5px] text-amber-600 font-medium flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          Unsaved edits — click Save to persist, or Regenerate PDF to save and re-render.
        </p>
      )}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={emptyLabel}
        rows={20}
        spellCheck={false}
        className="w-full font-mono text-[12px] leading-relaxed px-4 py-3 bg-white/40 rounded-2xl border border-slate-200/60 text-slate-800 outline-none focus:ring-2 focus:ring-accent-300/60 focus:bg-white/70 transition-all resize-y"
      />
    </div>
  );
}

function KeywordChips({ items, tone, label }) {
  if (!items?.length) return null;
  const tones = {
    required:  "bg-rose-100/80 text-rose-700 border-rose-200/60",
    preferred: "bg-amber-100/80 text-amber-700 border-amber-200/60",
    general:   "bg-slate-100/80 text-slate-600 border-slate-200/60",
  };
  return (
    <div className="space-y-1.5">
      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((kw, i) => (
          <span key={i} className={`pill border ${tones[tone] || tones.general}`}>
            {kw}
          </span>
        ))}
      </div>
    </div>
  );
}

function QuickTailorForm({ onCancel, onCreated, onError, initialJobUrl = "" }) {
  const { data: profile } = useProfile();
  const profileResume = (profile?.resume_text || "").trim();

  const [inputMode, setInputMode] = useState("paste"); // paste | upload
  const [resumeText, setResumeText] = useState("");
  const [source, setSource] = useState("none"); // "profile" | "upload" | "paste" | "none"
  const [jdMode, setJdMode] = useState(initialJobUrl ? "link" : "paste"); // paste | link
  const [jobDescription, setJobDescription] = useState("");
  const [jobUrl, setJobUrl] = useState(initialJobUrl);
  const [jdFetchError, setJdFetchError] = useState("");
  const [label, setLabel] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState("");
  const [parsedFileName, setParsedFileName] = useState("");
  const fileRef = useRef(null);
  const { mutateAsync, isPending } = useQuickTailor();
  const { mutateAsync: extractJd, isPending: fetchingJd } = useExtractJd();

  async function handleFetchJd() {
    const url = jobUrl.trim();
    if (!url) return;
    setJdFetchError("");
    try {
      const res = await extractJd(url);
      setJobDescription(res.job_description || res.text || "");
      if (!res.job_description && !res.text) {
        setJdFetchError("Fetched the page but couldn't isolate a job description — paste it manually.");
      }
    } catch (err) {
      const offline = err?.response?.status === 404;
      setJdFetchError(
        offline
          ? "JD fetch isn't available yet — paste the description instead."
          : err?.response?.data?.detail || "Couldn't fetch the JD from that link."
      );
    }
  }

  // Pre-fill from profile resume the first time it's available — only if the user
  // hasn't already typed/uploaded something. Don't keep overwriting on every render.
  useEffect(() => {
    if (profileResume && !resumeText && source === "none") {
      setResumeText(profileResume);
      setSource("profile");
    }
  }, [profileResume, resumeText, source]);

  function clearAndUseUpload() {
    setResumeText("");
    setSource("none");
    setParsedFileName("");
    setInputMode("upload");
    setTimeout(() => fileRef.current?.click(), 0);
  }

  function clearAndPasteFresh() {
    setResumeText("");
    setSource("none");
    setParsedFileName("");
    setInputMode("paste");
  }

  async function handleFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setParseError("Only PDF files are supported here.");
      return;
    }
    setParsing(true);
    setParseError("");
    try {
      const res = await profileApi.parsePdf(file);
      setResumeText(res.data.text || "");
      setParsedFileName(file.name);
      setSource("upload");
      setInputMode("paste"); // jump to text view so user can review/edit
    } catch (err) {
      setParseError(err?.response?.data?.detail || "Could not parse PDF");
    } finally {
      setParsing(false);
    }
  }

  async function handleSubmit(e) {
    e?.preventDefault?.();
    if (!resumeText.trim()) {
      onError?.("Resume text is required.");
      return;
    }
    try {
      const created = await mutateAsync({
        resume_text: resumeText,
        job_description: jobDescription.trim() || null,
        job_url: jdMode === "link" ? jobUrl.trim() || null : null,
        label: label.trim() || null,
      });
      onCreated?.(created);
    } catch (err) {
      onError?.(err?.response?.data?.detail || "Tailoring failed");
    }
  }

  const canSubmit = !isPending && !parsing && resumeText.trim().length > 0;

  return (
    <div className="max-w-2xl mx-auto px-6 py-6">
      <div className="mb-5">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-accent-600">
          NEW TAILORED RESUME
        </span>
        <h1 className="text-[22px] font-bold text-slate-900 tracking-tight mt-1">
          Tailor a resume against a JD
        </h1>
        <p className="text-[13px] text-slate-500 mt-1">
          Paste or upload a resume, paste a job description, and we'll produce a tailored ATS-formatted PDF — no application gets queued.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Resume input */}
        <div className="glass-subtle rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/40 flex items-center justify-between gap-2">
            <div>
              <h3 className="text-[13px] font-semibold text-slate-900">Resume</h3>
              {source === "profile" && (
                <p className="text-[11px] text-emerald-600 font-medium mt-0.5">
                  Loaded from your profile · edit below or
                  <button type="button" onClick={clearAndPasteFresh} className="ml-1 underline hover:text-emerald-700">paste fresh</button>
                  {" "}/
                  <button type="button" onClick={clearAndUseUpload} className="ml-1 underline hover:text-emerald-700">upload different</button>
                </p>
              )}
              {source === "upload" && parsedFileName && (
                <p className="text-[11px] text-emerald-600 font-medium mt-0.5">
                  Loaded from {parsedFileName} — edit before tailoring
                </p>
              )}
            </div>
            <div className="inline-flex items-center gap-1 bg-white/55 rounded-xl p-0.5">
              {[
                { key: "paste",  label: "Paste text" },
                { key: "upload", label: "Upload PDF" },
              ].map((m) => {
                const active = inputMode === m.key;
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => setInputMode(m.key)}
                    className={`px-3 py-1 rounded-lg text-[11.5px] font-semibold transition-all ${
                      active ? "bg-accent-600 text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="p-5">
            {inputMode === "paste" ? (
              <>
                <textarea
                  value={resumeText}
                  onChange={(e) => { setResumeText(e.target.value); if (source === "profile") setSource("paste"); }}
                  placeholder={profileResume ? "Loading your profile resume…" : "Paste your resume text here…"}
                  rows={12}
                  spellCheck={false}
                  className="w-full font-mono text-[12px] leading-relaxed px-4 py-3 bg-white/55 rounded-xl border border-slate-200/60 text-slate-800 outline-none focus:ring-2 focus:ring-accent-300/60 focus:bg-white/80 transition-all resize-y"
                />
                {!profileResume && (
                  <p className="text-[11px] text-slate-400 mt-2">
                    Tip: upload a resume PDF on your Profile and we'll pre-fill this on the next visit.
                  </p>
                )}
              </>
            ) : (
              <>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                    e.target.value = "";
                  }}
                />
                <div
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]); }}
                  className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-slate-200 hover:border-accent-400 hover:bg-white/40 cursor-pointer transition-all py-10 px-4"
                >
                  {parsing ? (
                    <>
                      <svg className="w-6 h-6 text-accent-500 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                      </svg>
                      <p className="text-[12px] text-slate-500">Extracting text from PDF…</p>
                    </>
                  ) : (
                    <>
                      <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <p className="text-[13px] font-semibold text-slate-700">Click or drag & drop a PDF resume</p>
                      <p className="text-[11px] text-slate-400">Text gets extracted and shown in the editor</p>
                    </>
                  )}
                </div>
                {parseError && <p className="text-[12px] text-rose-500 font-medium mt-2">{parseError}</p>}
              </>
            )}
          </div>
        </div>

        {/* Job Description */}
        <div className="glass-subtle rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/40 flex items-center justify-between gap-2">
            <div>
              <h3 className="text-[13px] font-semibold text-slate-900">Job Description <span className="text-slate-400 font-normal">· optional</span></h3>
              <p className="text-[11px] text-slate-500 mt-0.5">Paste a JD or fetch it from a job link. Leave blank to just reformat.</p>
            </div>
            <div className="inline-flex items-center gap-1 bg-white/55 rounded-xl p-0.5 flex-shrink-0">
              {[
                { key: "paste", label: "Paste JD" },
                { key: "link", label: "Job link" },
              ].map((m) => {
                const active = jdMode === m.key;
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => { setJdMode(m.key); setJdFetchError(""); }}
                    className={`px-3 py-1 rounded-lg text-[11.5px] font-semibold transition-all ${
                      active ? "bg-accent-600 text-white" : "text-slate-500 hover:text-slate-800"
                    }`}
                    style={active ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" } : undefined}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="p-5 space-y-3">
            {jdMode === "link" && (
              <div className="flex gap-2">
                <input
                  type="url"
                  value={jobUrl}
                  onChange={(e) => setJobUrl(e.target.value)}
                  placeholder="https://… (Greenhouse, Lever, Naukri, company careers page)"
                  className="input-glass flex-1"
                />
                <button
                  type="button"
                  onClick={handleFetchJd}
                  disabled={fetchingJd || !jobUrl.trim()}
                  className="btn-secondary !py-2 !px-3 text-[12px] flex-shrink-0"
                >
                  {fetchingJd ? (
                    <>
                      <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                        <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                      </svg>
                      Fetching…
                    </>
                  ) : "Fetch JD"}
                </button>
              </div>
            )}
            {jdFetchError && <p className="text-[12px] text-rose-500 font-medium">{jdFetchError}</p>}
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder={jdMode === "link" ? "Fetched job description appears here — review & edit before tailoring…" : "Paste the job description here…"}
              rows={8}
              spellCheck={false}
              className="w-full text-[12.5px] leading-relaxed px-4 py-3 bg-white/55 rounded-xl border border-slate-200/60 text-slate-800 outline-none focus:ring-2 focus:ring-accent-300/60 focus:bg-white/80 transition-all resize-y"
            />
            {jdMode === "link" && jobDescription && (
              <p className="text-[11px] text-emerald-600 font-medium">JD fetched · {jobDescription.length.toLocaleString()} characters — edit if needed, then tailor.</p>
            )}
          </div>
        </div>

        {/* Optional label */}
        <div className="glass-subtle rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/40">
            <h3 className="text-[13px] font-semibold text-slate-900">Label <span className="text-slate-400 font-normal">· optional</span></h3>
          </div>
          <div className="p-5">
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Senior ML — Stripe (2026-05-27)"
              className="input-glass"
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button type="submit" disabled={!canSubmit} className="btn-primary">
            {isPending ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                </svg>
                {jobDescription.trim() ? "Tailoring…" : "Formatting…"}
              </>
            ) : (
              <>
                {jobDescription.trim() ? "Tailor & Format" : "Format Resume"}
              </>
            )}
          </button>
          <button type="button" onClick={onCancel} className="btn-secondary">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}


export default function TailoredResumes() {
  const { data: list = [], isLoading } = useTailoredResumes();
  // A job-card "Tailor resume" deep-links here with ?job_url=… — open the
  // create form pre-seeded in Job-link mode.
  const initialJobUrl = new URLSearchParams(window.location.search).get("job_url") || "";
  const [selectedId, setSelectedId] = useState(null);
  const [creating, setCreating] = useState(!!initialJobUrl);
  const [tab, setTab] = useState("diff"); // diff | original | tailored | keywords
  const [editText, setEditText] = useState("");
  const [toast, setToast] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const deleteMutation = useDeleteTailoredResume();

  useEffect(() => {
    if (!creating && !selectedId && list.length > 0) {
      setSelectedId(list[0].id);
    }
  }, [list, selectedId, creating]);

  const { data: detail, isLoading: detailLoading } = useTailoredResume(selectedId);

  const update = useUpdateTailoredResume(selectedId);
  const retailor = useRetailorResume(selectedId);
  const regenerate = useRegeneratePdf(selectedId);

  // Reset edit buffer whenever we load a new tailored resume.
  useEffect(() => {
    setEditText(detail?.tailored_text || "");
  }, [detail?.id, detail?.tailored_text]);

  const dirty = (editText || "") !== (detail?.tailored_text || "");

  function showToast(type, message) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4500);
  }

  async function handleSave({ alsoRegeneratePdf } = {}) {
    try {
      await update.mutateAsync({ tailored_text: editText, regenerate_pdf: !!alsoRegeneratePdf });
      showToast("success", alsoRegeneratePdf ? "Saved and PDF regenerated." : "Saved.");
    } catch (err) {
      showToast("error", err?.response?.data?.detail || "Save failed");
    }
  }

  async function handleRetailor() {
    if (dirty) {
      const ok = window.confirm("You have unsaved edits. Re-tailoring will overwrite them. Continue?");
      if (!ok) return;
    }
    try {
      await retailor.mutateAsync();
      showToast("success", "Re-tailored with AI. Review and save (or regenerate PDF) to apply.");
    } catch (err) {
      showToast("error", err?.response?.data?.detail || "Re-tailoring failed");
    }
  }

  async function handleRegenerate() {
    if (dirty) {
      // Save edits first, then re-render
      try {
        await update.mutateAsync({ tailored_text: editText, regenerate_pdf: true });
        showToast("success", "Saved edits and regenerated PDF.");
        return;
      } catch (err) {
        showToast("error", err?.response?.data?.detail || "Save + regenerate failed");
        return;
      }
    }
    try {
      await regenerate.mutateAsync();
      showToast("success", "PDF regenerated.");
    } catch (err) {
      showToast("error", err?.response?.data?.detail || "Regenerate failed");
    }
  }

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const res = await tailoredResumesApi.pdf(detail.id);
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      const safe = (detail.job_title || detail.label || "resume").replace(/[^\w.-]+/g, "_");
      a.download = `${safe}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showToast("error", err?.response?.data?.detail || "Could not download PDF");
    } finally {
      setDownloading(false);
    }
  }

  const busy = update.isPending || retailor.isPending || regenerate.isPending;

  const diffStats = useMemo(() => {
    if (!detail?.diff_segments) return { adds: 0, removes: 0, equal: 0 };
    let adds = 0, removes = 0, equal = 0;
    for (const s of detail.diff_segments) {
      const lines = (s.text || "").split("\n").filter(Boolean).length || 1;
      if (s.type === "insert") adds += lines;
      else if (s.type === "delete") removes += lines;
      else equal += lines;
    }
    return { adds, removes, equal };
  }, [detail]);

  return (
    <div className="flex flex-col lg:flex-row h-full glass rounded-3xl overflow-hidden animate-fade-in relative min-h-0">
      {toast && (
        <div className="fixed top-5 right-5 z-50 glass-strong rounded-2xl px-4 py-3 max-w-sm flex items-center gap-2.5 animate-slide-up">
          <span className={`w-2 h-2 rounded-full ${toast.type === "success" ? "bg-emerald-500" : "bg-rose-500"}`} />
          <p className="text-[13px] font-medium text-slate-800">{toast.message}</p>
        </div>
      )}

      {/* Left list — top strip on mobile, sidebar on lg+ */}
      <aside className="flex-shrink-0 w-full lg:w-72 max-h-[38%] lg:max-h-none border-b lg:border-b-0 lg:border-r border-white/40 flex flex-col min-h-0">
        <div className="px-5 py-4 border-b border-white/40">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Tailored Resumes</h2>
              <p className="text-[11px] text-slate-400 mt-0.5">{list.length} total</p>
            </div>
            <button
              type="button"
              onClick={() => { setCreating(true); setSelectedId(null); }}
              className="btn-primary !py-1 !px-2.5 text-[11.5px]"
              title="Tailor a new resume against a JD"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              New
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          {isLoading ? (
            <div className="space-y-2 px-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-white/40 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-56 text-center px-4">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
                   style={{ background: "hsl(var(--muted))" }}>
                <svg className="w-6 h-6 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-sm text-slate-700 font-semibold">No tailored resumes yet</p>
              <p className="text-xs text-slate-400 mt-1">Each application with a JD generates one automatically.</p>
            </div>
          ) : (
            <ul className="space-y-1">
              {list.map((item) => {
                const active = item.id === selectedId;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => { setSelectedId(item.id); setCreating(false); }}
                      className={`group relative w-full text-left px-3 py-3 rounded-xl transition-all ${
                        active ? "bg-white/85 shadow-glass" : "hover:bg-white/55"
                      }`}
                    >
                      {active && (
                        <span aria-hidden
                          className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full"
                          style={{ background: "hsl(var(--primary))" }}
                        />
                      )}
                      <p className="text-[13px] font-semibold text-slate-900 truncate leading-tight">
                        {item.job_title || `Tailored Resume #${item.id}`}
                      </p>
                      <p className="text-[11.5px] text-slate-500 truncate mt-0.5">
                        {item.company || "—"}
                      </p>
                      <div className="flex items-center justify-between mt-1.5">
                        <div className="flex items-center gap-1">
                          {item.queued_by === "auto" && (
                            <span className="pill bg-accent-100/80 text-accent-700 border border-accent-200/60 !py-0.5 !px-1.5 text-[9.5px]">
                              AUTO
                            </span>
                          )}
                          {item.has_pdf && (
                            <span className="pill bg-emerald-100/80 text-emerald-700 border border-emerald-200/60 !py-0.5 !px-1.5 text-[9.5px]">
                              PDF
                            </span>
                          )}
                        </div>
                        <span className="text-[10.5px] text-slate-400 font-medium">{timeAgo(item.created_at)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      {/* Right detail */}
      <section className="flex-1 flex flex-col overflow-y-auto">
        {creating ? (
          <QuickTailorForm
            initialJobUrl={initialJobUrl}
            onCancel={() => setCreating(false)}
            onCreated={(created) => {
              setCreating(false);
              setSelectedId(created.id);
              setTab("diff");
              showToast("success", "Tailored resume ready.");
            }}
            onError={(msg) => showToast("error", msg)}
          />
        ) : !selectedId || detailLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              {selectedId ? (
                <div className="space-y-3">
                  <div className="w-8 h-8 mx-auto rounded-full border-2 border-accent-400 border-t-transparent animate-spin" />
                  <p className="text-[12.5px] text-slate-500">Loading diff…</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-[13px] text-slate-400">Select a tailored resume on the left, or:</p>
                  <button
                    onClick={() => setCreating(true)}
                    className="btn-primary"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                    Tailor a new resume
                  </button>
                </div>
              )}
            </div>
          </div>
        ) : detail ? (
          <>
            <header className="flex-shrink-0 px-6 py-5 border-b border-white/40">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <h1 className="text-[19px] font-bold text-slate-900 tracking-tight truncate">
                    {detail.job_title || "Tailored Resume"}
                  </h1>
                  <p className="text-[13px] text-slate-500 mt-0.5">
                    {detail.company || "—"}
                    {detail.application_status && (
                      <span className="ml-2 text-slate-400">
                        · {detail.application_status} · {timeAgo(detail.created_at)}
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 flex-shrink-0 justify-end">
                  <button
                    type="button"
                    onClick={handleRetailor}
                    disabled={busy}
                    className="btn-secondary !py-1.5 !px-3 text-[12px]"
                    title="Re-run the AI tailoring against this job description"
                  >
                    {retailor.isPending ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                          <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                        </svg>
                        Tailoring…
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                        Re-tailor with AI
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSave({ alsoRegeneratePdf: false })}
                    disabled={busy || !dirty}
                    className="btn-secondary !py-1.5 !px-3 text-[12px]"
                  >
                    {update.isPending && !regenerate.isPending ? "Saving…" : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={handleRegenerate}
                    disabled={busy}
                    className="btn-primary !py-1.5 !px-3 text-[12px]"
                    title="Re-render PDF from the current tailored text"
                  >
                    {regenerate.isPending || (update.isPending && dirty) ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                          <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                        </svg>
                        Rendering…
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        {dirty ? "Save & Regenerate" : "Regenerate PDF"}
                      </>
                    )}
                  </button>
                  {detail.has_pdf && (
                    <button
                      type="button"
                      onClick={handleDownloadPdf}
                      disabled={downloading}
                      className="btn-secondary !py-1.5 !px-3 text-[12px] disabled:opacity-60"
                    >
                      <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                      {downloading ? "Downloading…" : "PDF"}
                    </button>
                  )}
                  {detail.job_url && (
                    <a
                      href={detail.job_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary !py-1.5 !px-3 text-[12px]"
                    >
                      <svg className="w-3.5 h-3.5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                      Job
                    </a>
                  )}
                  {!detail.application_id && (
                    <button
                      type="button"
                      onClick={async () => {
                        if (!window.confirm("Delete this tailored resume? Standalone entries are gone for good.")) return;
                        try {
                          await deleteMutation.mutateAsync(detail.id);
                          setSelectedId(null);
                          showToast("success", "Deleted.");
                        } catch (err) {
                          showToast("error", err?.response?.data?.detail || "Delete failed");
                        }
                      }}
                      className="p-1.5 text-slate-400 hover:text-rose-500 rounded-lg hover:bg-rose-50/70 transition-colors"
                      title="Delete this standalone tailored resume"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round"
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7h6m2 0a1 1 0 00-1-1h-4a1 1 0 00-1 1H5" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 mt-3">
                <StatBadge value={`+${diffStats.adds}`} label="lines added" tone="add" />
                <StatBadge value={`−${diffStats.removes}`} label="lines removed" tone="remove" />
                <StatBadge value={diffStats.equal} label="unchanged" tone="keep" />
                <AtsBadge score={detail.ats_score} />
              </div>

              {/* Tabs */}
              <div className="inline-flex items-center gap-1 glass-subtle rounded-2xl p-1 mt-4">
                {[
                  { key: "diff",     label: "Diff" },
                  { key: "tailored", label: "Tailored" },
                  { key: "original", label: "Original" },
                  { key: "keywords", label: "Keywords" },
                ].map((t) => {
                  const active = tab === t.key;
                  return (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className={`relative px-4 py-1.5 rounded-xl text-[12.5px] font-semibold transition-all ${
                        active ? "text-white" : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {active && (
                        <span aria-hidden className="absolute inset-0 rounded-xl"
                              style={{ background: "hsl(var(--primary))" }} />
                      )}
                      <span className="relative z-10">{t.label}</span>
                    </button>
                  );
                })}
              </div>
            </header>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              {tab === "diff" && <DiffView segments={detail.diff_segments} />}
              {tab === "tailored" && (
                <EditableTailoredView
                  value={editText}
                  dirty={dirty}
                  onChange={setEditText}
                  emptyLabel="Paste or edit the tailored resume text here. Save to persist, or Save & Regenerate to also rebuild the PDF."
                />
              )}
              {tab === "original" && <FullTextView text={detail.original_text} emptyLabel="No original resume saved on profile." />}
              {tab === "keywords" && (
                <div className="space-y-5">
                  {detail.ats_score != null && (
                    <div className="flex items-center gap-2">
                      <AtsBadge score={detail.ats_score} />
                      <span className="text-[11.5px] text-slate-400">How well the tailored resume covers the JD's keywords</span>
                    </div>
                  )}
                  <KeywordChips items={detail.missing_keywords} tone="required" label="Missing Keywords — add these to improve ATS coverage" />
                  <KeywordChips items={detail.keywords?.required_skills} tone="required" label="Required Skills" />
                  <KeywordChips items={detail.keywords?.preferred_skills} tone="preferred" label="Preferred Skills" />
                  <KeywordChips items={detail.keywords?.keywords} tone="general" label="Keywords" />
                  {detail.keywords?.deal_breakers?.length > 0 && (
                    <KeywordChips items={detail.keywords.deal_breakers} tone="required" label="Deal Breakers" />
                  )}
                  {detail.keywords?.years_experience && (
                    <div>
                      <div className="text-[10.5px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
                        Years of Experience
                      </div>
                      <p className="text-[13px] text-slate-700">{detail.keywords.years_experience}</p>
                    </div>
                  )}
                  {(!detail.keywords ||
                    Object.keys(detail.keywords).length === 0) && (
                    <p className="text-[12.5px] text-slate-400 text-center py-8">
                      No keywords were extracted for this application.
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}
