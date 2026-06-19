import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi, authApi } from "../services/api";
import AdminUserDrawer from "../components/AdminUserDrawer";

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

function Stat({ label, value }) {
  return (
    <div className="text-center">
      <div className="text-[15px] font-semibold text-slate-900 tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div>
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

  return (
    <div className="p-6 lg:p-8 max-w-[1400px] mx-auto">
      <div className="flex items-end justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Admin · Users</h1>
          <p className="text-sm text-slate-500 mt-1">
            Watch every user, their progress, and their credentials. View-only — passwords can't be edited.
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold text-slate-900 tabular-nums">{data?.total ?? 0}</div>
          <div className="text-[11px] uppercase tracking-wide text-slate-400">Total users</div>
        </div>
      </div>

      {isError && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 text-sm mb-4">
          {error?.response?.data?.detail || "Failed to load users."}
        </div>
      )}

      <div className="glass rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-slate-400 border-b border-slate-200/70">
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
                  className="border-b border-slate-100 hover:bg-white/40 cursor-pointer"
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