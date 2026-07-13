import { useState } from "react";
import { authApi } from "../services/api";

/**
 * Shown once, right after a first-time "Continue with Google" sign-up. The user
 * picks a username + password (so they can log in directly next time, and so the
 * admin has a credential to show). On success the fresh token is stored and
 * onDone() is called.
 */
export default function SetCredentialsModal({ onDone }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (username.trim().length < 3) return setError("Username must be at least 3 characters.");
    if (password.length < 6) return setError("Password must be at least 6 characters.");
    if (password !== confirm) return setError("Passwords don't match.");

    setLoading(true);
    try {
      const { data } = await authApi.setupCredentials({ username: username.trim(), password });
      if (data?.access_token) localStorage.setItem("token", data.access_token);
      onDone();
    } catch (err) {
      setError(err.response?.data?.detail || "Couldn't save your credentials. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/45 backdrop-blur-sm">
      <div className="w-full max-w-sm glass-strong rounded-3xl p-8 animate-slide-up">
        <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Finish setting up</h2>
        <p className="mt-1 text-sm text-slate-500">
          Choose a username and password. You'll use these to sign in next time.
        </p>

        <form onSubmit={handleSubmit} className="mt-7 space-y-4">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
              Username
            </label>
            <input
              type="text"
              placeholder="your_handle"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input-glass"
            />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                Password
              </label>
              <button
                type="button"
                onClick={() => setShow((s) => !s)}
                className="text-[11px] font-semibold text-brand hover:opacity-80 uppercase tracking-wider"
              >
                {show ? "Hide" : "Show"}
              </button>
            </div>
            <input
              type={show ? "text" : "password"}
              placeholder="••••••••"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-glass"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
              Confirm password
            </label>
            <input
              type={show ? "text" : "password"}
              placeholder="••••••••"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="input-glass"
            />
          </div>

          {error && (
            <div className="flex items-start gap-2.5 rounded-xl px-3.5 py-2.5"
                 style={{
                   background: "rgba(254, 226, 226, 0.65)",
                   border: "1px solid rgba(239, 68, 68, 0.25)",
                   backdropFilter: "blur(8px)",
                 }}>
              <svg className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-rose-700 leading-snug">{error}</p>
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full mt-1">
            {loading ? "Saving…" : "Save & continue"}
          </button>
        </form>
      </div>
    </div>
  );
}
