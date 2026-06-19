import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "../../hooks/useTheme";
import { authApi } from "../../services/api";
import { Wordmark } from "../brand/Logo";

// Chosen brand mark: the AK emblem (interlocked ligature in a gradient badge).
const BRAND_VARIANT = "ak-emblem";

const NAV = [
  {
    path: "/",
    label: "Dashboard",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    path: "/discovered-jobs",
    label: "Jobs",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z" />
      </svg>
    ),
  },
  {
    path: "/tailored-resumes",
    label: "Resume",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    path: "/email-auto",
    label: "Emails",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    path: "/tracker",
    label: "Job Tracker",
    icon: (
      <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M4 6h4v4H4V6zm6 0h4v4h-4V6zm6 0h4v4h-4V6zM4 14h4v4H4v-4zm6 0h4v4h-4v-4zm6 0h4v4h-4v-4z" />
      </svg>
    ),
  },
];

const ADMIN_LINK = {
  path: "/admin",
  label: "Admin",
  icon: (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
};

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { dark, toggle } = useTheme();
  // Admins get a management-only sidebar (just the Admin console); normal users
  // get the full job-seeker nav. Token-gated; ignored when logged out.
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    enabled: !!localStorage.getItem("token"),
    staleTime: 5 * 60 * 1000,
  });
  const navItems = me?.is_admin ? [ADMIN_LINK] : NAV;

  function logout() {
    onClose();
    localStorage.removeItem("token");
    navigate("/login");
  }

  return (
    <>
      {/* Mobile backdrop */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity lg:hidden ${
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 m-2 w-64 sidebar-panel rounded-3xl flex flex-col overflow-hidden
          transition-transform duration-300 ease-out
          lg:static lg:z-auto lg:m-0 lg:w-60 lg:flex-shrink-0 lg:translate-x-0
          ${mobileOpen ? "translate-x-0" : "-translate-x-[110%]"}
        `}
      >
      {/* Brand */}
      <div className="px-5 pt-6 pb-5 flex items-center justify-between">
        <Wordmark variant={BRAND_VARIANT} size={34} />
        {/* Close button — mobile only */}
        <button
          onClick={onClose}
          aria-label="Close menu"
          className="lg:hidden p-1.5 -mr-1 rounded-lg text-slate-500 hover:bg-muted"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 space-y-1 overflow-y-auto">
        {navItems.map(({ path, label, icon }) => {
          const active =
            path === "/"
              ? pathname === "/"
              : pathname === path || pathname.startsWith(path + "/");
          return (
            <Link
              key={path}
              to={path}
              onClick={onClose}
              aria-current={active ? "page" : undefined}
              className={`relative flex items-center gap-3 px-3 py-2 rounded-lg text-[13.5px] font-medium transition-colors ${
                active
                  ? "text-brand font-semibold"
                  : "text-slate-600 hover:text-slate-900 hover:bg-muted/60"
              }`}
              style={active ? { background: "hsl(var(--brand) / 0.1)" } : undefined}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-brand" />
              )}
              <span className="flex items-center gap-3">
                {icon}
                <span>{label}</span>
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Dark mode toggle + Logout */}
      <div className="px-3 pb-4 pt-2 space-y-0.5">
        <button
          onClick={toggle}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium text-slate-500 hover:text-slate-900 hover:bg-white/55 w-full transition-all duration-200"
        >
          {dark ? (
            /* Sun icon */
            <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M12 3v1m0 16v1m8.66-9h-1M4.34 12h-1m15.07-6.07-.71.71M6.34 17.66l-.71.71M17.66 17.66l-.71-.71M6.34 6.34l-.71-.71M12 8a4 4 0 100 8 4 4 0 000-8z" />
            </svg>
          ) : (
            /* Moon icon */
            <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M21 12.79A9 9 0 1111.21 3a7 7 0 109.79 9.79z" />
            </svg>
          )}
          {dark ? "Light mode" : "Dark mode"}
        </button>

        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium text-slate-500 hover:text-rose-600 hover:bg-rose-50/70 w-full transition-all duration-200"
        >
          <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.7}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Sign out
        </button>
      </div>
      </aside>
    </>
  );
}
