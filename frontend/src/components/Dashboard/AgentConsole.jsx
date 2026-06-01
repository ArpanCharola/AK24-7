import { useEffect, useRef, useState } from "react";
import { useAgentWebSocket } from "../../hooks/useWebSocket";
import OTPModal from "../HITL/OTPModal";

// Ordered pipeline steps shown in the live progress tracker. Keys match the
// backend `step` event names emitted from _run_application / progress.py.
const STEP_DEFS = [
  { key: "tailoring", label: "Tailor" },
  { key: "pdf", label: "PDF" },
  { key: "cover_letter", label: "Cover letter" },
  { key: "submitting", label: "Submit" },
];

function StepTracker({ steps }) {
  if (!steps || Object.keys(steps).length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 px-4 py-2 border-b border-white/[0.06] flex-shrink-0 overflow-x-auto"
         style={{ background: "rgba(15, 14, 30, 0.4)" }}>
      {STEP_DEFS.map(({ key, label }, i) => {
        const s = steps[key];           // undefined = not started
        const state = s?.state;
        const dot =
          state === "done" ? "bg-emerald-400"
          : state === "error" ? "bg-rose-400"
          : state === "start" ? "bg-sky-400 animate-pulse"
          : "bg-slate-600";
        const text =
          state === "done" ? "text-emerald-300/90"
          : state === "error" ? "text-rose-300/90"
          : state === "start" ? "text-sky-300/90"
          : "text-slate-500";
        return (
          <div key={key} className="flex items-center gap-1.5">
            {i > 0 && <span className="w-3 h-px bg-white/10" />}
            <span className="inline-flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
              <span className={`text-[11px] font-medium ${text}`} title={s?.message || ""}>
                {label}
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function AgentConsole({ jobId }) {
  const { logs, screenshots, requireOtp, connected, resetOtp, steps } = useAgentWebSocket(jobId);
  const logEndRef = useRef(null);
  // null = follow the latest screenshot; a number pins the viewer to that index.
  const [pinnedIdx, setPinnedIdx] = useState(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Reset the pinned view when switching applications.
  useEffect(() => { setPinnedIdx(null); }, [jobId]);

  const viewIdx = pinnedIdx ?? (screenshots.length - 1);
  const current = screenshots.length ? screenshots[viewIdx] : null;

  if (!jobId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-8 relative">
        <div className="absolute inset-0 opacity-20"
             style={{
               background:
                 "radial-gradient(ellipse at top, rgba(120,120,135,0.12) 0%, transparent 60%)",
             }}
        />
        <div className="relative z-10">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 mx-auto"
               style={{
                 background: "hsl(var(--muted))",
                 border: "1px solid rgba(255,255,255,0.06)",
               }}>
            <svg className="w-8 h-8 text-accent-400/80" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.4}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <p className="text-slate-200 text-sm font-semibold tracking-tight">Agent Console</p>
          <p className="text-slate-500 text-[12.5px] mt-1.5 max-w-xs">
            Select an application to watch logs and screenshots stream in real time
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {requireOtp && <OTPModal jobId={jobId} onClose={resetOtp} />}

      {/* Status bar */}
      <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-white/[0.06] flex-shrink-0"
           style={{ background: "rgba(15, 14, 30, 0.6)" }}>
        <span className={`relative flex items-center justify-center w-2 h-2 ${connected ? "" : ""}`}>
          <span className={`absolute w-2 h-2 rounded-full ${connected ? "bg-emerald-400" : "bg-slate-600"}`} />
          {connected && (
            <span className="absolute w-2 h-2 rounded-full bg-emerald-400 animate-ping opacity-60" />
          )}
        </span>
        <span className="text-[11.5px] text-slate-400 font-medium">
          {connected ? "Live" : "Disconnected"}
          <span className="text-slate-600 mx-1.5">·</span>
          <span className="text-slate-300">Application #{jobId}</span>
        </span>
        {connected && (
          <span className="ml-auto text-[10px] text-emerald-400/70 font-mono tracking-wider uppercase">
            ● Recording
          </span>
        )}
      </div>

      {/* Pipeline progress tracker (tailor → PDF → cover letter → submit) */}
      <StepTracker steps={steps} />

      {/* Split: logs + screenshot */}
      <div className="flex flex-1 overflow-hidden">
        {/* Logs */}
        <div className="w-1/2 overflow-y-auto p-4 font-mono text-[11.5px] space-y-0.5 leading-relaxed border-r border-white/[0.06]">
          {logs.length === 0 ? (
            <p className="text-slate-600 italic">Waiting for agent output…</p>
          ) : (
            logs.map((line, i) => (
              <p key={i} className="text-emerald-300/85">
                <span className="text-slate-600 mr-3 select-none">
                  {String(i + 1).padStart(3, "0")}
                </span>
                {line}
              </p>
            ))
          )}
          <div ref={logEndRef} />
        </div>

        {/* Screenshot gallery — the application being completed, step by step */}
        <div className="w-1/2 flex flex-col" style={{ background: "rgba(15, 14, 30, 0.4)" }}>
          <div className="flex-1 flex items-center justify-center p-4 min-h-0 relative">
            {current ? (
              <>
                <img
                  src={current.url}
                  alt={current.caption || "Agent screenshot"}
                  className="max-w-full max-h-full object-contain rounded-xl ring-1 ring-white/10"
                  style={{ boxShadow: "0 20px 60px -20px rgba(0,0,0,0.6)" }}
                />
                <div className="absolute top-5 left-5 flex items-center gap-2">
                  {current.caption && (
                    <span className="px-2 py-0.5 rounded-md bg-black/60 text-[11px] text-slate-200 backdrop-blur">
                      {current.caption}
                    </span>
                  )}
                  <span className="px-2 py-0.5 rounded-md bg-black/60 text-[10px] text-slate-400 backdrop-blur font-mono">
                    {viewIdx + 1}/{screenshots.length}
                  </span>
                  {pinnedIdx !== null && (
                    <button
                      onClick={() => setPinnedIdx(null)}
                      className="px-2 py-0.5 rounded-md bg-accent-500/80 text-[10px] text-white"
                    >
                      ▶ Live
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div className="text-center">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3"
                     style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)" }}>
                  <svg className="w-6 h-6 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <p className="text-slate-500 text-[12px]">No screenshot yet</p>
              </div>
            )}
          </div>

          {/* Thumbnail filmstrip of every captured step */}
          {screenshots.length > 1 && (
            <div className="flex gap-2 overflow-x-auto px-3 py-2 border-t border-white/[0.06]">
              {screenshots.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setPinnedIdx(i === screenshots.length - 1 ? null : i)}
                  title={s.caption}
                  className={`flex-shrink-0 rounded-md overflow-hidden ring-1 transition-all ${
                    i === viewIdx ? "ring-accent-400" : "ring-white/10 opacity-60 hover:opacity-100"
                  }`}
                >
                  <img src={s.url} alt={s.caption || `step ${i + 1}`} className="h-12 w-auto object-cover" />
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
