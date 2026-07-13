import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { authApi } from "../services/api";

export default function Settings() {
  const navigate = useNavigate();
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
        <p className="mt-1 text-sm text-muted-foreground">Account and integrations.</p>

        <div className="glass rounded-2xl p-5 mt-5">
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted-foreground">Account</h2>
          <div className="space-y-1 text-sm">
            <p className="font-medium text-foreground">{me?.full_name || me?.username || "—"}</p>
            <p className="text-muted-foreground">{me?.email}</p>
          </div>
          <button onClick={() => navigate("/profile")} className="btn-secondary mt-4">Edit profile</button>
        </div>

        <div className="glass rounded-2xl p-5 mt-4 flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted-foreground">Email</h2>
            <p className="mt-1 text-sm text-foreground">{me?.gmail_email ? `Connected · ${me.gmail_email}` : "Not connected"}</p>
          </div>
          <button onClick={() => navigate("/email-auto")} className="btn-secondary">Manage</button>
        </div>

        <div className="glass rounded-2xl p-5 mt-4 flex items-center justify-between">
          <div>
            <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted-foreground">Session</h2>
            <p className="mt-1 text-sm text-muted-foreground">Sign out of this device.</p>
          </div>
          <button onClick={logout} className="btn-secondary text-[13px]">Sign out</button>
        </div>
      </div>
    </div>
  );
}
