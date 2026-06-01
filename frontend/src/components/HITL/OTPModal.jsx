import { useState } from "react";
import { useSubmitOtp } from "../../hooks/useApplications";

export default function OTPModal({ jobId, onClose }) {
  const [otp, setOtp] = useState("");
  const { mutate: submitOtp, isPending } = useSubmitOtp();

  function handleSubmit(e) {
    e.preventDefault();
    submitOtp({ job_id: jobId, otp }, { onSuccess: onClose });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 animate-fade-in"
      style={{
        background: "rgba(15, 23, 42, 0.35)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
      }}
    >
      <div className="glass-strong rounded-3xl p-7 w-full max-w-sm animate-slide-up">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-2xl flex items-center justify-center"
               style={{ background: "hsl(var(--muted))" }}>
            <svg className="w-5 h-5 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 5.024c.149-.32.29-.642.423-.967M13 8a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-[17px] font-semibold text-slate-900 tracking-tight">OTP Required</h2>
            <p className="text-[12px] text-slate-500 mt-0.5">Agent is waiting to continue</p>
          </div>
        </div>

        <p className="text-[13px] text-slate-600 leading-relaxed mt-3 mb-5">
          The portal is requesting a verification code. Check your email and enter the OTP below.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            value={otp}
            onChange={(e) => setOtp(e.target.value)}
            placeholder="Enter OTP"
            className="input-glass text-center text-lg tracking-[0.4em] font-mono"
            autoFocus
            required
          />
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={onClose} className="btn-ghost">
              Cancel
            </button>
            <button type="submit" disabled={isPending} className="btn-primary">
              {isPending ? "Submitting…" : "Submit"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
