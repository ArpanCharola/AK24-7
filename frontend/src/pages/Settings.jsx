import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { authApi } from "../services/api";
import { useTheme } from "../hooks/useTheme";

export default function Settings() {
  const navigate = useNavigate();
  const { dark, toggle } = useTheme();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    enabled: !!localStorage.getItem("token"),
    staleTime: 5 * 60 * 1000,
  });

  const logout = () => { localStorage.removeItem("token"); navigate("/login"); };

  return (
    <div className="h-full overflow-y-auto animate-fade-in">
      <div className="max-w-2xl mx-auto p-1 sm:p-2">
        <h1 className="text-2xl font-display font-bold text-foreground tracking-tight">Settings</h1>
        <p className="text-sm text-slate-500 mt-1">Account, appearance, and integrations.</p>

        <div className="glass rounded-2xl p-5 mt-5">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Account</h2>
          <div className="space-y-1 text-sm">
            <p className="text-foreground font-medium">{me?.full_name || me?.username || "—"}</p>
            <p className="text-slate-500">{me?.email}</p>
          </div>
          <button onClick={() => navigate("/profile")} className="btn-secondary mt-4">Edit profile</button>
        </div>

        <div className="glass rounded-2xl p-5 mt-4 flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-500">Appearance</h2>
            <p className="text-sm text-foreground mt-1">{dark ? "Dark mode" : "Light mode"}</p>
          </div>
          <button onClick={toggle} className="btn-secondary">{dark ? "Switch to light" : "Switch to dark"}</button>
        </div>

        <div className="glass rounded-2xl p-5 mt-4 flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-500">Email</h2>
            <p className="text-sm text-foreground mt-1">{me?.gmail_email ? `Connected · ${me.gmail_email}` : "Not connected"}</p>
          </div>
          <button onClick={() => navigate("/email-auto")} className="btn-secondary">Manage</button>
        </div>

        <div className="glass rounded-2xl p-5 mt-4 flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-slate-500">Session</h2>
            <p className="text-sm text-slate-500 mt-1">Sign out of this device.</p>
          </div>
          <button onClick={logout} className="px-4 py-2 rounded-xl text-[13px] font-semibold text-rose-600 hover:bg-rose-50/70 transition-colors">Sign out</button>
        </div>
      </div>
    </div>
  );
}
