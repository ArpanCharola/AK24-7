import { useEffect, useState } from "react";
import { NavLink, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Menu, X } from "lucide-react";
import { authApi } from "../../services/api";
import { Wordmark } from "../brand/Logo";
import AvatarMenu from "./AvatarMenu";

const USER_NAV = [
  ["/dashboard", "Dashboard"], ["/jobs", "Jobs"],
  ["/email-auto", "Email"], ["/tracker", "Job Tracker"],
];

export default function TopNav() {
  const [open, setOpen] = useState(false);
  const { data: me } = useQuery({
    queryKey: ["me"], queryFn: () => authApi.me().then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
  const nav = me?.is_admin ? [["/admin", "Admin"]] : USER_NAV;
  const home = me?.is_admin ? "/admin" : "/dashboard";

  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, []);

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
          <AvatarMenu />
          <button
            className="icon-button mobile-trigger"
            onClick={() => setOpen((current) => !current)}
            aria-label={open ? "Close navigation" : "Open navigation"}
            aria-controls="mobile-primary-navigation"
            aria-expanded={open}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      {open && <nav id="mobile-primary-navigation" className="mobile-nav" aria-label="Mobile navigation">
        {nav.map(([path, label]) => <NavLink key={path} to={path} onClick={() => setOpen(false)}>{label}</NavLink>)}
      </nav>}
    </header>
  );
}
