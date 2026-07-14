import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "../services/api";

function fmtDate(s) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d) ? "—" : d.toLocaleString();
}

// A labelled key/value row.
function Field({ label, value, mono }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className={`text-[13px] text-slate-800 break-words ${mono ? "font-mono" : ""}`}>
        {empty ? <span className="text-slate-300">—</span> : String(value)}
      </span>
    </div>
  );
}

function Section({ title, count, children }) {
  return (
    <div className="mt-6">
      <h3 className="text-[12px] font-bold uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-2">
        {title}
        {count != null && (
          <span className="text-[11px] font-semibold text-slate-400">({count})</span>
        )}
      </h3>
      {children}
    </div>
  );
}

// Renders a JSON-ish list field (skills / work_experience / education / etc.)
// defensively — handles arrays of strings or arrays of objects.
function StructuredBlock({ value }) {
  if (value == null || (Array.isArray(value) && value.length === 0)) {
    return <p className="text-[13px] text-slate-300">—</p>;
  }
  if (Array.isArray(value)) {
    // Array of strings → chips
    if (value.every((v) => typeof v === "string")) {
      return (
        <div className="flex flex-wrap gap-1.5">
          {value.map((v, i) => (
            <span key={i} className="text-[12px] bg-slate-100 text-slate-700 rounded-full px-2 py-0.5">{v}</span>
          ))}
        </div>
      );
    }
    // Array of objects → cards
    return (
      <div className="space-y-2">
        {value.map((item, i) => (
          <div key={i} className="rounded-lg bg-slate-50 border border-slate-100 px-3 py-2">
            {typeof item === "object" && item !== null ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {Object.entries(item).map(([k, v]) => (
                  <div key={k} className="text-[12px]">
                    <span className="text-slate-400">{k}: </span>
                    <span className="text-slate-700">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-[12px] text-slate-700">{String(item)}</span>
            )}
          </div>
        ))}
      </div>
    );
  }
  return <p className="text-[13px] text-slate-700 whitespace-pre-wrap">{String(value)}</p>;
}

function MiniTable({ columns, rows, render }) {
  if (!rows || rows.length === 0) {
    return <p className="text-[13px] text-slate-300">None</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-100">
      <table className="w-full text-left text-[12.5px]">
        <thead>
          <tr className="text-[10px] uppercase tracking-wide text-slate-400 bg-slate-50">
            {columns.map((c) => <th key={c} className="px-3 py-1.5 font-semibold">{c}</th>)}
          </tr>
        </thead>
        <tbody>{rows.map(render)}</tbody>
      </table>
    </div>
  );
}

export default function AdminUserDrawer({ userId, onClose }) {
  const [showPw, setShowPw] = useState(false);
  const { data: u, isLoading, isError, error } = useQuery({
    queryKey: ["admin-user", userId],
    queryFn: () => adminApi.getUser(userId).then((r) => r.data),
    enabled: userId != null,
  });

  return (
    <div className="fixed inset-0 z-[90] flex justify-end admin-drawer-shell">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="admin-drawer relative h-full w-full max-w-2xl overflow-y-auto animate-slide-up">
        <div className="admin-drawer__head sticky top-0 z-10 flex items-center justify-between px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              {u?.full_name || u?.email || "User"}
            </h2>
            <p className="text-[12px] text-slate-500">{u?.email}</p>
          </div>
          <button onClick={onClose} className="rounded-xl p-2 text-slate-500 hover:bg-muted" aria-label="Close">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-5 admin-drawer__body">
          {isLoading && <p className="text-slate-400">Loading…</p>}
          {isError && (
            <p className="text-rose-600">{error?.response?.data?.detail || "Failed to load user."}</p>
          )}

          {u && (
            <>
              {/* Account */}
              <Section title="Account">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="User ID" value={u.id} />
                  <Field label="Role" value={u.is_admin ? "Admin" : "User"} />
                  <Field label="Username" value={u.username} />
                  <Field label="Status" value={u.is_active ? "Active" : "Disabled"} />
                  <Field label="Credentials set" value={u.credentials_set ? "Yes" : "No"} />
                  <Field label="Joined" value={fmtDate(u.created_at)} />
                  <div className="flex flex-col col-span-2">
                    <span className="text-[10px] uppercase tracking-wide text-slate-400">Raw password</span>
                    {u.raw_password ? (
                      <span className="text-[13px] font-mono text-slate-800 flex items-center gap-2">
                        {showPw ? u.raw_password : "•".repeat(Math.min(u.raw_password.length, 12))}
                        <button onClick={() => setShowPw((s) => !s)} className="text-[11px] font-semibold text-accent-600">
                          {showPw ? "Hide" : "Show"}
                        </button>
                      </span>
                    ) : (
                      <span className="text-[13px] italic text-slate-400">Google — no password</span>
                    )}
                  </div>
                </div>
              </Section>

              {/* Gmail */}
              <Section title="Gmail">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Connected" value={u.gmail_connected ? "Yes" : "No"} />
                  <Field label="Gmail email" value={u.gmail_email} />
                  <div className="col-span-2"><Field label="Scopes" value={u.gmail_scopes} mono /></div>
                </div>
              </Section>

              {/* Profile */}
              <Section title="Profile">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Phone" value={u.profile?.phone} />
                  <Field label="Location" value={u.profile?.location} />
                  <Field label="LinkedIn" value={u.profile?.linkedin_url} />
                  <Field label="GitHub" value={u.profile?.github_url} />
                  <Field label="Website" value={u.profile?.website_url} />
                  <Field label="Current CTC (LPA)" value={u.profile?.current_ctc_lpa} />
                  <Field label="Expected CTC (LPA)" value={u.profile?.expected_ctc_lpa} />
                  <Field label="Notice (days)" value={u.profile?.notice_period_days} />
                  <Field label="Preferred locations" value={u.profile?.preferred_locations} />
                  <Field label="Auto-apply" value={u.profile?.auto_apply_enabled ? `On (cap ${u.profile?.daily_auto_apply_cap})` : "Off"} />
                  <Field label="Portal email" value={u.profile?.portal_email} />
                  <Field label="Portal password" value={u.profile?.portal_password} mono />
                </div>
                {u.profile?.profile_summary && (
                  <div className="mt-3">
                    <span className="text-[10px] uppercase tracking-wide text-slate-400">Summary</span>
                    <p className="text-[13px] text-slate-700 whitespace-pre-wrap mt-1">{u.profile.profile_summary}</p>
                  </div>
                )}
                <div className="mt-3">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">Skills</span>
                  <div className="mt-1"><StructuredBlock value={u.profile?.skills} /></div>
                </div>
                <div className="mt-3">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">Work experience</span>
                  <div className="mt-1"><StructuredBlock value={u.profile?.work_experience} /></div>
                </div>
                <div className="mt-3">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">Education</span>
                  <div className="mt-1"><StructuredBlock value={u.profile?.education} /></div>
                </div>
                <div className="mt-3">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">Projects</span>
                  <div className="mt-1"><StructuredBlock value={u.profile?.projects} /></div>
                </div>
                <div className="mt-3">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">Certifications</span>
                  <div className="mt-1"><StructuredBlock value={u.profile?.certifications} /></div>
                </div>
                {u.profile?.resume_text && (
                  <details className="mt-3">
                    <summary className="text-[12px] font-semibold text-accent-600 cursor-pointer">Resume text</summary>
                    <pre className="mt-2 text-[12px] text-slate-700 whitespace-pre-wrap bg-slate-50 rounded-lg p-3 max-h-72 overflow-y-auto">{u.profile.resume_text}</pre>
                  </details>
                )}
              </Section>

              {/* Activity */}
              <Section title="Applications" count={u.applications?.length}>
                <MiniTable
                  columns={["Role", "Company", "Status", "Stage", "When"]}
                  rows={u.applications}
                  render={(a) => (
                    <tr key={a.id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{a.job_title || "—"}</td>
                      <td className="px-3 py-1.5">{a.company || "—"}</td>
                      <td className="px-3 py-1.5">{a.status || "—"}</td>
                      <td className="px-3 py-1.5">{a.stage || "—"}</td>
                      <td className="px-3 py-1.5 text-slate-500">{fmtDate(a.created_at)}</td>
                    </tr>
                  )}
                />
              </Section>

              <Section title="Search profiles" count={u.job_searches?.length}>
                <MiniTable
                  columns={["Name", "Roles", "Locations", "Active", "Last run"]}
                  rows={u.job_searches}
                  render={(s) => (
                    <tr key={s.id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{s.name}</td>
                      <td className="px-3 py-1.5">{s.target_roles || "—"}</td>
                      <td className="px-3 py-1.5">{s.locations || "—"}</td>
                      <td className="px-3 py-1.5">{s.is_active ? "Yes" : "No"}</td>
                      <td className="px-3 py-1.5 text-slate-500">{fmtDate(s.last_run_at)}</td>
                    </tr>
                  )}
                />
              </Section>

              <Section title="Discovered jobs" count={u.discovered_jobs?.length}>
                <MiniTable
                  columns={["Title", "Company", "Source", "Score", "Status"]}
                  rows={u.discovered_jobs}
                  render={(d) => (
                    <tr key={d.id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{d.title || "—"}</td>
                      <td className="px-3 py-1.5">{d.company || "—"}</td>
                      <td className="px-3 py-1.5">{d.source || "—"}</td>
                      <td className="px-3 py-1.5">{d.match_score ?? "—"}</td>
                      <td className="px-3 py-1.5">{d.status || "—"}</td>
                    </tr>
                  )}
                />
              </Section>

              <Section title="Tailored resumes" count={u.tailored_resumes?.length}>
                <MiniTable
                  columns={["Label", "Job URL", "When"]}
                  rows={u.tailored_resumes}
                  render={(r) => (
                    <tr key={r.id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{r.label || `#${r.id}`}</td>
                      <td className="px-3 py-1.5 truncate max-w-[220px]">{r.job_url || "—"}</td>
                      <td className="px-3 py-1.5 text-slate-500">{fmtDate(r.created_at)}</td>
                    </tr>
                  )}
                />
              </Section>

              <Section title="Sent emails" count={u.sent_emails?.length}>
                <MiniTable
                  columns={["To", "Subject", "Kind", "When"]}
                  rows={u.sent_emails}
                  render={(e) => (
                    <tr key={e.id} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">{e.to_addr}</td>
                      <td className="px-3 py-1.5 truncate max-w-[220px]">{e.subject || "—"}</td>
                      <td className="px-3 py-1.5">{e.kind || "—"}</td>
                      <td className="px-3 py-1.5 text-slate-500">{fmtDate(e.sent_at)}</td>
                    </tr>
                  )}
                />
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}