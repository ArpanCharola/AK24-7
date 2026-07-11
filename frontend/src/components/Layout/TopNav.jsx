import { useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Menu, X, Moon, Sun } from "lucide-react";
import { authApi } from "../../services/api";
import { useTheme } from "../../hooks/useTheme";
import { Wordmark } from "../brand/Logo";
import AvatarMenu from "./AvatarMenu";

const USER_NAV = [
  ["/dashboard", "Dashboard"], ["/jobs", "Jobs"],
  ["/email-auto", "Email"], ["/tracker", "Job Tracker"],
];

export default function TopNav() {
  const [open, setOpen] = useState(false);
  const { dark, toggle } = useTheme();
  const { data: me } = useQuery({
    queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
  const nav = me?.is_admin ? [["/admin", "Admin"]] : USER_NAV;
  const home = me?.is_admin ? "/admin" : "/dashboard";

  return (
    <header className="editorial-nav">
      <div className="nav-inner">
        <Link to={home} className="nav-brand" aria-label="AK24/7 home">
          <Wordmark variant="ak-emblem" size={34} tagline={null} />
        </Link>
        <nav className="desktop-nav" aria-label="Primary navigation">
          {nav.map(([path, label]) => <NavLink key={path} to={path}>{label}</NavLink>)}
        </nav>
        <div className="nav-actions">
          <button className="icon-button" onClick={toggle} aria-label={dark ? "Use light theme" : "Use dark theme"}>
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <AvatarMenu />
          <button className="icon-button mobile-trigger" onClick={() => setOpen(!open)} aria-label="Open navigation">
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      {open && <nav className="mobile-nav" aria-label="Mobile navigation">
        {nav.map(([path, label]) => <NavLink key={path} to={path} onClick={() => setOpen(false)}>{label}</NavLink>)}
      </nav>}
    </header>
  );
}
