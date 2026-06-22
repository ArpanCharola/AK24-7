import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Search, Mail, Table2, ShieldCheck,
  Sun, Moon, LogOut, X,
} from "lucide-react";
import { useTheme } from "../../hooks/useTheme";
import { authApi } from "../../services/api";
import { Wordmark } from "../brand/Logo";

const BRAND_VARIANT = "ak-emblem";

const NAV = [
  { path: "/dashboard",     label: "Dashboard",   icon: LayoutDashboard },
  { path: "/jobs",          label: "Jobs",        icon: Search },
  { path: "/email-auto",    label: "Email",       icon: Mail },
  { path: "/tracker",       label: "Job Tracker", icon: Table2 },
];

const ADMIN_LINK = { path: "/admin", label: "Admin", icon: ShieldCheck };

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
  const navigate = useNavigate();
  const { dark, toggle } = useTheme();
  // Admins get a management-only sidebar; normal users get the full job-seeker nav.
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
          fixed inset-y-0 left-0 z-50 w-64 flex flex-col overflow-hidden
          sidebar-panel border-r
          transition-transform duration-300 ease-out
          lg:static lg:z-auto lg:w-60 lg:flex-shrink-0 lg:translate-x-0
          ${mobileOpen ? "translate-x-0" : "-translate-x-[110%]"}
        `}
      >
        {/* Brand — flush to the top, same height as the topbar (h-14). */}
        <div className="h-14 px-5 flex items-center justify-between border-b border-sidebar-border/70 shrink-0">
          <Wordmark variant={BRAND_VARIANT} size={30} />
          <button
            onClick={onClose}
            aria-label="Close menu"
            className="lg:hidden p-1.5 -mr-1 rounded-lg text-muted-foreground hover:bg-muted"
          >
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              onClick={onClose}
              className={({ isActive }) =>
                `relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium transition-all duration-150 ${
                  isActive
                    ? "text-brand font-semibold bg-brand/10"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-gradient-to-b from-brand to-brand-accent" />
                  )}
                  <Icon size={18} strokeWidth={1.75} className="shrink-0" />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Dark mode toggle + Logout */}
        <div className="px-3 pb-4 pt-2 space-y-0.5 border-t border-sidebar-border/70">
          <button
            onClick={toggle}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 w-full transition-all duration-150"
          >
            {dark ? <Sun size={18} strokeWidth={1.75} /> : <Moon size={18} strokeWidth={1.75} />}
            {dark ? "Light mode" : "Dark mode"}
          </button>
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium text-muted-foreground hover:text-danger hover:bg-danger/10 w-full transition-all duration-150"
          >
            <LogOut size={18} strokeWidth={1.75} />
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
