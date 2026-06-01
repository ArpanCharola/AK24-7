import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../services/api";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const GOOGLE_LOGIN_URL = `${API_BASE}/email/login`;

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Handle the return from "Sign in with Google": the backend redirects here
  // with ?token=<jwt> on success, or ?google=<reason> on failure.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      localStorage.setItem("token", token);
      navigate("/", { replace: true });
      return;
    }
    const g = params.get("google");
    if (g) {
      const msgs = {
        denied: "Google sign-in was cancelled.",
        error: "Google sign-in failed — please try again.",
        unconfigured: "Google sign-in isn't configured on the server yet.",
      };
      setError(msgs[g] || "Google sign-in failed.");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const fn = mode === "login" ? authApi.login : authApi.register;
      const { data } = await fn(form);
      localStorage.setItem("token", data.access_token);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  const features = [
    "Discovers real jobs across India from free sources",
    "AI scores each role against your profile with why-fit",
    "Tailors an ATS-optimized resume from a JD or job link",
    "Orion copilot for interview prep & skill-gap advice",
  ];

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <div className="relative grid lg:grid-cols-2 min-h-screen">
        {/* Left: brand / pitch */}
        <div className="hidden lg:flex flex-col justify-between p-10 xl:p-14">
          <div className="flex items-center gap-3">
            <div className="relative w-10 h-10 rounded-2xl flex items-center justify-center overflow-hidden"
                 style={{ background: "hsl(var(--primary))" }}>
              <svg className="w-5 h-5 text-white relative z-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <div className="absolute inset-0 bg-white/20 mix-blend-overlay" />
            </div>
            <div className="leading-tight">
              <div className="text-base font-semibold text-slate-900 tracking-tight">AK24/7Jobs</div>
              <div className="text-[10px] uppercase tracking-[0.16em] text-slate-400 font-medium">Jobs in India</div>
            </div>
          </div>

          <div className="max-w-md animate-slide-up">
            <h1 className="text-[44px] leading-[1.05] font-bold text-slate-900 tracking-tight">
              Find your next role <span className="text-gradient">across India</span>
              <br /> — matched to you.
            </h1>
            <p className="mt-5 text-[15px] leading-relaxed text-slate-600">
              From your resume, AK24/7Jobs discovers real jobs across India, ranks them
              by fit with clear why-fit and skill gaps, and tailors an ATS-ready resume
              for every application.
            </p>

            <ul className="mt-8 space-y-3">
              {features.map((f) => (
                <li key={f} className="flex items-start gap-3">
                  <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full flex items-center justify-center"
                        style={{ background: "hsl(var(--muted))" }}>
                    <svg className="w-3 h-3 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <span className="text-[14px] text-slate-700">{f}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="text-[11px] text-slate-400 tracking-wide">
            Powered by OpenAI · Built for serious job seekers
          </div>
        </div>

        {/* Right: glass auth card */}
        <div className="flex items-center justify-center p-6 lg:p-10">
          <div className="w-full max-w-sm glass-strong rounded-3xl p-8 animate-slide-up">
            {/* Mobile brand */}
            <div className="flex items-center gap-2.5 mb-6 lg:hidden">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                   style={{ background: "hsl(var(--primary))" }}>
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <span className="font-semibold text-slate-900 text-base tracking-tight">AK24/7Jobs</span>
            </div>

            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
              {mode === "login" ? "Welcome back" : "Create account"}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {mode === "login" ? "Sign in to your account" : "Get started in seconds"}
            </p>

            <form onSubmit={handleSubmit} className="mt-7 space-y-4">
              {mode === "register" && (
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                    Full name
                  </label>
                  <input
                    type="text"
                    placeholder="Jane Doe"
                    required
                    value={form.full_name}
                    onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                    className="input-glass"
                  />
                </div>
              )}
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                  Email
                </label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="input-glass"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                  Password
                </label>
                <input
                  type="password"
                  placeholder="••••••••"
                  required
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
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
                {loading ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                    </svg>
                    Loading…
                  </>
                ) : (
                  mode === "login" ? "Sign in" : "Create account"
                )}
              </button>
            </form>

            <div className="flex items-center gap-3 my-5">
              <div className="flex-1 h-px bg-slate-200/70" />
              <span className="text-[11px] text-slate-400 uppercase tracking-wider">or</span>
              <div className="flex-1 h-px bg-slate-200/70" />
            </div>

            <button
              type="button"
              onClick={() => { window.location.href = GOOGLE_LOGIN_URL; }}
              className="w-full flex items-center justify-center gap-2.5 py-2.5 rounded-xl border border-slate-200 bg-white/80 hover:bg-white text-slate-700 font-semibold text-sm transition-colors"
            >
              <svg className="w-[18px] h-[18px]" viewBox="0 0 48 48" aria-hidden>
                <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.3-.3-3.5z"/>
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 16.3 4.5 9.7 8.9 6.3 14.7z"/>
                <path fill="#4CAF50" d="M24 43.5c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.6 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.6 39 16.2 43.5 24 43.5z"/>
                <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C39.9 36.3 43.5 30.7 43.5 24c0-1.2-.1-2.3-.3-3.5z"/>
              </svg>
              Sign in with Google
            </button>
            <p className="text-center text-[11px] text-slate-400 mt-2">
              Also connects your inbox to auto-track application replies
            </p>

            <p className="text-center text-sm text-slate-500 mt-6">
              {mode === "login" ? "Don't have an account?" : "Already have an account?"}{" "}
              <button
                onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}
                className="text-accent-600 font-semibold hover:text-accent-700 transition-colors"
              >
                {mode === "login" ? "Sign up" : "Sign in"}
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
