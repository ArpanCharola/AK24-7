import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../services/api";
import SetCredentialsModal from "../components/SetCredentialsModal";
import { Wordmark } from "../components/brand/Logo";
import Footer from "../components/Layout/Footer";
import { Eye, EyeOff } from "lucide-react";

// Chosen brand mark: the AK emblem (interlocked ligature in a gradient badge).
const BRAND_VARIANT = "ak-emblem";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
// First-time sign-up happens through Google. The backend find-or-creates the
// account, then redirects back here with ?token=...&setup=1 so we can collect a
// username + password.
const GOOGLE_LOGIN_URL = `${API_BASE}/email/login`;

export default function Login() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ identifier: "", password: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Handle the return from "Continue with Google".
  useEffect(() => {
    document.documentElement.classList.remove("dark");
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const setup = params.get("setup");
    if (token) {
      localStorage.setItem("token", token);
      // Clear the query string so a refresh doesn't re-trigger.
      window.history.replaceState({}, "", window.location.pathname);
      if (setup === "1") {
        setNeedsSetup(true); // open the username/password popup
      } else {
        navigate("/dashboard", { replace: true });
      }
      return;
    }
    const g = params.get("google");
    if (g) {
      window.history.replaceState({}, "", window.location.pathname);
      if (g === "exists") {
        setNotice("You already have an account — please log in with your email/username and password.");
      } else {
        const msgs = {
          denied: "Google sign-in was cancelled.",
          error: "Google sign-in failed — please try again.",
          unconfigured: "Google sign-in isn't configured on the server yet.",
        };
        setError(msgs[g] || "Google sign-in failed.");
      }
    }
  }, [navigate]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      const { data } = await authApi.login(form);
      localStorage.setItem("token", data.access_token);
      // Admins go to their management console, not the job-seeker dashboard.
      let isAdmin = false;
      try {
        const me = await authApi.me();
        isAdmin = !!me.data?.is_admin;
      } catch { /* fall back to home on /me failure */ }
      navigate(isAdmin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  const features = [
    "Discovers real jobs across India from free sources",
    "AI scores each role against your profile with why-fit",
    "Tracks applications and email updates in one focused workspace",
  ];

  return (
    <div className="login-page">
      {needsSetup && (
        <SetCredentialsModal onDone={() => navigate("/dashboard", { replace: true })} />
      )}
      <div className="relative z-10 grid lg:grid-cols-2 login-grid">
        {/* Left: brand / pitch */}
        <div className="login-story hidden lg:flex flex-col p-10 xl:p-14">
          <Wordmark variant={BRAND_VARIANT} size={42} />

          <div className="login-story-copy max-w-md animate-slide-up my-auto py-10">
            <span className="editorial-kicker">The career edition · India</span>
            <h1>Find work<br /><em>worth showing up for.</em></h1>
            <p className="mt-5 text-[15px] leading-relaxed text-slate-600">
              Drop in your resume and AK24/7Jobs surfaces real openings from across India,
              ranking each by how well it fits — with the why and the skill gaps —
              so you always know where to apply next.
            </p>

            <ul className="mt-8 space-y-3">
              {features.map((f) => (
                <li key={f} className="flex items-start gap-3">
                  <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full flex items-center justify-center"
                        style={{ background: "hsl(var(--success) / 0.14)" }}>
                    <svg className="w-3 h-3 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <span className="text-[14px] text-slate-700">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right: glass auth card */}
        <div className="login-form-side flex items-center justify-center p-6 lg:p-10">
          <div className="login-card w-full max-w-sm glass-strong p-8 animate-slide-up">
            {/* Mobile brand */}
            <div className="mb-6 lg:hidden">
              <Wordmark variant={BRAND_VARIANT} size={36} tagline={null} />
            </div>

            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Welcome back</h2>
            <p className="mt-1 text-sm text-slate-500">Sign in to your account</p>

            <form onSubmit={handleSubmit} className="mt-7 space-y-4">
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                  Email or username
                </label>
                <input
                  type="text"
                  placeholder="you@example.com"
                  required
                  value={form.identifier}
                  onChange={(e) => setForm({ ...form, identifier: e.target.value })}
                  className="input-glass"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1.5">
                  Password
                </label>
                <div className="password-field">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  required
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="input-glass !pr-12"
                />
                <button type="button" onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword} className="password-toggle">
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
                </div>
              </div>

              {notice && (
                <div className="flex items-start gap-2.5 rounded-xl px-3.5 py-2.5"
                     style={{
                       background: "rgba(219, 234, 254, 0.7)",
                       border: "1px solid rgba(59, 130, 246, 0.25)",
                       backdropFilter: "blur(8px)",
                     }}>
                  <svg className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-sm text-blue-700 leading-snug">{notice}</p>
                </div>
              )}

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
                  "Sign in"
                )}
              </button>
            </form>

            <div className="flex items-center gap-3 my-5">
              <div className="flex-1 h-px bg-border" />
              <span className="text-[11px] text-slate-400 uppercase tracking-wider">new here?</span>
              <div className="flex-1 h-px bg-border" />
            </div>

            <button
              type="button"
              onClick={() => { window.location.href = GOOGLE_LOGIN_URL; }}
              className="w-full flex items-center justify-center gap-2.5 py-2.5 rounded-xl border border-border bg-card hover:bg-muted text-foreground font-semibold text-sm transition-colors"
            >
              <svg className="w-[18px] h-[18px]" viewBox="0 0 48 48" aria-hidden>
                <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.3-.3-3.5z"/>
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 16.3 4.5 9.7 8.9 6.3 14.7z"/>
                <path fill="#4CAF50" d="M24 43.5c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.6 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.6 39 16.2 43.5 24 43.5z"/>
                <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C39.9 36.3 43.5 30.7 43.5 24c0-1.2-.1-2.3-.3-3.5z"/>
              </svg>
              Continue with Google
            </button>
            <p className="text-center text-[11px] text-slate-400 mt-3">
              First time? Sign up with Google, then set a username &amp; password.
            </p>
          </div>
        </div>
      </div>
      <Footer publicView />
    </div>
  );
}
