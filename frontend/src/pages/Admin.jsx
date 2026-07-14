import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, authApi } from "../services/api";
import AdminUserDrawer from "../components/AdminUserDrawer";
import { AnalyticsOverview, JobWarehouse, SourceRuns } from "../components/AdminAnalytics";
import { Activity, Shield, Users } from "lucide-react";

function AdminStat({ label, value, note, icon: Icon }) {
  return (
    <article className="admin-stat-card">
      <div>
        <p className="admin-stat-label">{label}</p>
        <strong>{value}</strong>
        <span>{note}</span>
      </div>
      <span className="admin-stat-icon">
        <Icon size={18} />
      </span>
    </article>
  );
}

function RoleBadge({ isAdmin }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold ${
        isAdmin ? "bg-primary/10 text-primary" : "bg-slate-100 text-slate-600"
      }`}
    >
      {isAdmin ? "Admin" : "User"}
    </span>
  );
}

// Raw password cell — masked by default, reveal + copy. Read-only (no edit, by
// design). Shows "Google — no password" when the user hasn't set one yet.
function PasswordCell({ value }) {
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!value) {
    return <span className="text-[12px] italic text-slate-400">Google — no password</span>;
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* clipboard blocked — ignore */ }
  }

  return (
    <div className="flex items-center gap-2">
      <code className="text-[12.5px] font-mono text-slate-800 bg-slate-100 rounded px-1.5 py-0.5">
        {show ? value : "•".repeat(Math.min(value.length, 10))}
      </code>
      <button
        onClick={() => setShow((s) => !s)}
        className="text-[11px] font-semibold text-accent-600 hover:text-accent-700"
        title={show ? "Hide" : "Reveal"}
      >
        {show ? "Hide" : "Show"}
      </button>
      <button
        onClick={copy}
        className="text-[11px] font-semibold text-slate-500 hover:text-slate-800"
        title="Copy"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export default function Admin() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Guard: only admins may view this page.
  const { data: meData, isLoading: meLoading, isError: meError } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
  });

  useEffect(() => {
    if (!meLoading && (meError || (meData && !meData.is_admin))) {
      navigate("/", { replace: true });
    }
  }, [meLoading, meError, meData, navigate]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => adminApi.listUsers().then((r) => r.data),
    enabled: !!meData?.is_admin,
  });

  const [openId, setOpenId] = useState(null);
  const [tab, setTab] = useState("overview");

  const del = useMutation({
    mutationFn: (id) => adminApi.deleteUser(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, isActive }) => adminApi.setActive(id, isActive),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  function handleDelete(u) {
    if (window.confirm(`Delete ${u.email} and ALL their data? This cannot be undone.`)) {
      del.mutate(u.id);
    }
  }

  if (meLoading || (meData?.is_admin && isLoading)) {
    return <div className="p-8 text-slate-500">Loading…</div>;
  }
  if (!meData?.is_admin) return null; // redirecting

  const users = data?.users || [];
  const activeUsers = users.filter((user) => user.is_active).length;
  const gmailConnected = users.filter((user) => user.gmail_connected).length;
  const pendingSetup = users.filter((user) => !user.credentials_set).length;

  if (tab === "overview") return <div className="page-wrap admin-shell"><AdminTabs tab={tab} setTab={setTab}/><AnalyticsOverview /></div>;
  if (tab === "jobs") return <div className="page-wrap admin-shell"><AdminTabs tab={tab} setTab={setTab}/><JobWarehouse /></div>;
  if (tab === "runs") return <div className="page-wrap admin-shell"><AdminTabs tab={tab} setTab={setTab}/><SourceRuns /></div>;

  return (
    <div className="page-wrap admin-shell">
      <section className="admin-hero">
        <div>
          <p className="admin-eyebrow">CONTROL ROOM</p>
          <h1>Admin · users</h1>
          <p>
            Review account access, setup progress, Gmail linkage, and user-level activity from one cleaner operations surface.
          </p>
        </div>
        <div className="admin-hero-pill">single admin workspace · live data</div>
      </section>

      <AdminTabs tab={tab} setTab={setTab} />

      <section className="admin-user-summary">
        <AdminStat label="Total users" value={data?.total ?? 0} note="Accounts on this deployment" icon={Users} />
        <AdminStat label="Active" value={activeUsers} note="Enabled and able to sign in" icon={Activity} />
        <AdminStat label="Gmail connected" value={gmailConnected} note="Inbox and send features available" icon={Shield} />
        <AdminStat label="Setup pending" value={pendingSetup} note="Signed up but credentials still incomplete" icon={Users} />
      </section>

      {isError && (
        <div className="admin-state admin-state--error">
          {error?.response?.data?.detail || "Failed to load users."}
        </div>
      )}

      <div className="admin-users-card">
        <div className="admin-users-card__head">
          <div>
            <h2>User directory</h2>
            <p>View-only passwords, access state, counts, and quick user actions.</p>
          </div>
          <div className="admin-total-pill">{data?.total ?? 0} users</div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm admin-users-table">
            <thead>
              <tr>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Username</th>
                <th className="px-4 py-3 font-semibold">Role</th>
                <th className="px-4 py-3 font-semibold">Raw password</th>
                <th className="px-4 py-3 font-semibold text-center">Apps</th>
                <th className="px-4 py-3 font-semibold text-center">Searches</th>
                <th className="px-4 py-3 font-semibold text-center">Discovered</th>
                <th className="px-4 py-3 font-semibold text-center">Resumes</th>
                <th className="px-4 py-3 font-semibold text-center">Emails</th>
                <th className="px-4 py-3 font-semibold">Joined</th>
                <th className="px-4 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  onClick={() => setOpenId(u.id)}
                  className="cursor-pointer border-b border-border/80"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{u.full_name || "—"}</div>
                    <div className="text-[12px] text-slate-500">{u.email}</div>
                    {!u.credentials_set && (
                      <span className="text-[10px] text-amber-600">setup incomplete</span>
                    )}
                    {!u.is_active && (
                      <span className="ml-1 text-[10px] text-rose-600">disabled</span>
                    )}
                    {u.gmail_connected && (
                      <span className="ml-1 text-[10px] text-emerald-600">Gmail connected</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-700">{u.username || "—"}</td>
                  <td className="px-4 py-3"><RoleBadge isAdmin={u.is_admin} /></td>
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <PasswordCell value={u.raw_password} />
                  </td>
                  <td className="px-4 py-3 text-center tabular-nums">{u.progress?.applications ?? 0}</td>
                  <td className="px-4 py-3 text-center tabular-nums">{u.progress?.job_searches ?? 0}</td>
                  <td className="px-4 py-3 text-center tabular-nums">{u.progress?.discovered_jobs ?? 0}</td>
                  <td className="px-4 py-3 text-center tabular-nums">{u.progress?.tailored_resumes ?? 0}</td>
                  <td className="px-4 py-3 text-center tabular-nums">{u.progress?.sent_emails ?? 0}</td>
                  <td className="px-4 py-3 text-[12px] text-slate-500">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => setOpenId(u.id)}
                      className="text-[12px] font-semibold text-accent-600 hover:text-accent-700 mr-3"
                    >
                      View
                    </button>
                    {u.is_admin ? (
                      <span className="text-[11px] text-slate-400">protected</span>
                    ) : (
                      <>
                        <button
                          onClick={() => toggleActive.mutate({ id: u.id, isActive: !u.is_active })}
                          disabled={toggleActive.isPending}
                          className="text-[12px] font-semibold text-slate-500 hover:text-slate-800 disabled:opacity-50 mr-3"
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                        <button
                          onClick={() => handleDelete(u)}
                          disabled={del.isPending}
                          className="text-[12px] font-semibold text-rose-600 hover:text-rose-700 disabled:opacity-50"
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-4 py-10 text-center text-slate-400">
                    No users yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {openId != null && (
        <AdminUserDrawer userId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function AdminTabs({ tab, setTab }) {
  return <nav className="admin-tabs" aria-label="Admin sections">
    {[['overview','Overview'],['jobs','All jobs'],['runs','Sources & runs'],['users','Users']].map(([id,label]) =>
      <button key={id} onClick={() => setTab(id)} className={tab === id ? 'active' : ''} aria-selected={tab === id}>{label}</button>
    )}
  </nav>;
}
