import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  Eye,
  EyeOff,
  MailCheck,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import { authApi } from "../services/api";
import SetCredentialsModal from "../components/SetCredentialsModal";
import { Wordmark } from "../components/brand/Logo";
import { apiBaseUrl } from "../lib/runtime-config";

const BRAND_VARIANT = "ak-emblem";
const API_BASE = apiBaseUrl();
const GOOGLE_LOGIN_URL = `${API_BASE}/email/login`;

const FEATURES = [
  {
    title: "Ranked roles",
    copy: "Prioritize openings by fit, freshness, and location.",
    icon: Sparkles,
  },
  {
    title: "India search",
    copy: "Filter by city, remote preference, and experience level.",
    icon: Target,
  },
  {
    title: "Mail to tracker",
    copy: "Keep recruiter replies and applications connected.",
    icon: ShieldCheck,
  },
];

const WORKFLOW = [
  ["Search", "Find direct openings"],
  ["Review", "Compare match signals"],
  ["Track", "Move applications forward"],
];

export default function Login() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ identifier: "", password: "" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    document.documentElement.classList.remove("dark");
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const setup = params.get("setup");
    if (token) {
      localStorage.setItem("token", token);
      window.history.replaceState({}, "", window.location.pathname);
      if (setup === "1") setNeedsSetup(true);
      else navigate("/dashboard", { replace: true });
      return;
    }
    const g = params.get("google");
    if (g) {
      window.history.replaceState({}, "", window.location.pathname);
      if (g === "exists") {
        setNotice("You already have an account. Sign in with your email or username and password.");
      } else {
        const msgs = {
          denied: "Google sign-in was cancelled.",
          error: "Google sign-in failed. Please try again.",
          unconfigured: "Google sign-in is not configured on the server yet.",
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
      let isAdmin = false;
      try {
        const me = await authApi.me();
        isAdmin = !!me.data?.is_admin;
      } catch {
        // ignore /me fallback and go home
      }
      navigate(isAdmin ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      {needsSetup && <SetCredentialsModal onDone={() => navigate("/dashboard", { replace: true })} />}

      <div className="relative z-10 grid login-grid lg:grid-cols-[1fr_0.86fr]">
        <section className="login-story hidden flex-col justify-center px-10 py-10 lg:flex xl:px-12 xl:py-12">
          <div className="login-story-header">
            <Wordmark variant={BRAND_VARIANT} size={38} tagline="career workflow" />
            <div className="login-story-pill-row mt-5" aria-hidden="true">
              <span className="login-story-pill">Jobs</span>
              <span className="login-story-pill">Inbox</span>
              <span className="login-story-pill">Tracker</span>
            </div>
          </div>

          <div className="login-story-copy my-auto max-w-2xl py-8">
            <span className="editorial-kicker">Focused job search workspace</span>
            <h1>
              Search smarter.
              <br />
              <em>Apply with context.</em>
            </h1>
            <p className="max-w-xl text-[15px] leading-7">
              A calmer workspace for finding relevant roles, reading recruiter mail, and keeping your application pipeline current.
            </p>

            <div className="login-feature-grid mt-7 grid gap-3 sm:grid-cols-3">
              {FEATURES.map(({ title, copy, icon: Icon }) => (
                <div key={title} className="login-feature-card">
                  <span className="login-feature-icon">
                    <Icon size={17} />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-foreground">{title}</p>
                    <p className="mt-1 text-[12px] leading-5 text-muted-foreground">{copy}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="login-workflow mt-7">
              {WORKFLOW.map(([title, copy], index) => (
                <div key={title} className="login-workflow-step">
                  <span>{index + 1}</span>
                  <div>
                    <p>{title}</p>
                    <small>{copy}</small>
                  </div>
                  {index < WORKFLOW.length - 1 && <ArrowRight size={15} aria-hidden="true" />}
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="login-form-side flex items-center justify-center px-4 py-4 sm:px-6 sm:py-6 lg:px-10 lg:py-8">
          <div className="login-card w-full glass-strong p-6 animate-slide-up sm:p-7">
            <div className="mb-6 flex items-start justify-between gap-4">
              <Wordmark variant={BRAND_VARIANT} size={34} tagline={null} />
              <span className="login-secure-badge">
                <ShieldCheck size={13} /> Secure
              </span>
            </div>

            <div>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-[30px]">Welcome back</h2>
              <p className="mt-2 text-sm text-slate-500">
                Sign in to continue your job search workflow.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-600">
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
                <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-slate-600">
                  Password
                </label>
                <div className="password-field">
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Password"
                    required
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    className="input-glass !pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="password-toggle"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {notice && (
                <div className="rounded-xl border border-info/25 bg-info/10 px-3.5 py-3 text-sm text-info">
                  {notice}
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-danger/25 bg-danger/10 px-3.5 py-3 text-sm text-danger">
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading} className="btn-gradient w-full !rounded-xl !py-3 text-[13px] font-semibold">
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </form>

            <div className="my-5 flex items-center gap-3">
              <div className="h-px flex-1 bg-border" />
              <span className="text-[10px] uppercase tracking-wider text-slate-400">or</span>
              <div className="h-px flex-1 bg-border" />
            </div>

            <button
              type="button"
              onClick={() => {
                window.location.href = GOOGLE_LOGIN_URL;
              }}
              className="google-button"
            >
              <svg className="h-[18px] w-[18px]" viewBox="0 0 48 48" aria-hidden>
                <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.3-.3-3.5z" />
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.5 29.3 4.5 24 4.5 16.3 4.5 9.7 8.9 6.3 14.7z" />
                <path fill="#4CAF50" d="M24 43.5c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.5-4.6 2.4-7.2 2.4-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.6 39 16.2 43.5 24 43.5z" />
                <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C39.9 36.3 43.5 30.7 43.5 24c0-1.2-.1-2.3-.3-3.5z" />
              </svg>
              Continue with Google
            </button>
            <p className="mt-3 text-center text-[11px] leading-5 text-slate-400">
              First time? Use Google once, then set your username and password.
            </p>

            <div className="login-note mt-5 rounded-2xl border border-border bg-muted/35 px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">Workspace</p>
              <div className="mt-3 grid gap-2 text-[13px] text-muted-foreground sm:grid-cols-2">
                <div className="flex items-center gap-2"><BriefcaseBusiness size={15} className="text-brand" /> Job matches</div>
                <div className="flex items-center gap-2"><MailCheck size={15} className="text-brand" /> Recruiter inbox</div>
                <div className="flex items-center gap-2"><CheckCircle2 size={15} className="text-brand" /> Tracker stages</div>
                <div className="flex items-center gap-2"><Target size={15} className="text-brand" /> Search targets</div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
