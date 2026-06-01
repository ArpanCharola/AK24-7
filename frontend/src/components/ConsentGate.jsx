/* Non-dismissible disclaimer gate ported from Automail.

The first time a signed-in user lands on the app, we show a four-card
disclaimer explaining what AK24/7Jobs does with their inbox. They have to
accept (POST /api/auth/consent) before any background sync runs. The gate
re-appears if we later add a Gmail scope that wasn't included at the time
of the original consent.
*/
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";

// The Gmail OAuth scopes the merged app expects. Kept in lockstep with the
// backend's app/services/gmail_client.py SCOPES list. If the backend adds a
// new scope, add it here too — the gate will detect the gap on existing users
// and re-prompt for consent so the disclaimer accurately covers everything
// we'll actually do.
const SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify";
const SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send";
const REQUIRED_SCOPES = [
  "openid",
  "https://www.googleapis.com/auth/userinfo.email",
  SCOPE_MODIFY,
  SCOPE_SEND,
];

function hasAllRequiredScopes(consented) {
  if (!consented) return false;
  const have = new Set(String(consented).split(/\s+/).filter(Boolean));
  return REQUIRED_SCOPES.every((s) => have.has(s));
}

const ConsentContext = createContext({
  granted: false,
  loading: true,
  refresh: async () => {},
  hasGmail: false,
});

export function useConsent() {
  return useContext(ConsentContext);
}

export default function ConsentGate({ children }) {
  const [state, setState] = useState({ loading: true, granted: false, hasGmail: false });

  const refresh = useCallback(async () => {
    // No token → no gate (e.g. the /login page itself).
    if (!localStorage.getItem("token")) {
      setState({ loading: false, granted: true, hasGmail: false });
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      const hasGmail = !!data.gmail_email;
      // No Gmail connection yet — the user clicked Sign in with Google but
      // their token doesn't have Gmail scopes. The modal would be premature;
      // let them through and let the email-auto page guide them.
      if (!hasGmail) {
        setState({ loading: false, granted: true, hasGmail: false });
        return;
      }
      const ok = !!data.consent_given_at && hasAllRequiredScopes(data.consented_scopes);
      setState({ loading: false, granted: ok, hasGmail: true });
    } catch (err) {
      // Fail closed for /me errors that aren't auth issues — show the modal
      // rather than letting background sync run on an unknown state.
      if (err?.response?.status === 401) {
        setState({ loading: false, granted: true, hasGmail: false });
      } else {
        setState({ loading: false, granted: false, hasGmail: true });
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <ConsentContext.Provider value={{ ...state, refresh }}>
      {children}
      {state.hasGmail && !state.granted && !state.loading && <ConsentModal onAccept={refresh} />}
    </ConsentContext.Provider>
  );
}

function ConsentModal({ onAccept }) {
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);
  const navigate = useNavigate();

  const deny = () => {
    localStorage.removeItem("token");
    navigate("/login", { replace: true });
  };

  const accept = async () => {
    setSaving(true);
    setErr(null);
    try {
      await api.post("/auth/consent");
      await onAccept();
    } catch (e) {
      setErr(e?.response?.data?.detail || "Couldn't save consent. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl glass-strong rounded-3xl p-7 max-h-[90vh] overflow-y-auto">
        <h2 className="text-[22px] font-bold text-slate-900 tracking-tight">Before we begin</h2>
        <p className="text-[13.5px] text-slate-500 mt-1.5">
          AK24/7Jobs works with your Gmail inbox. Please take a moment to read what that means.
        </p>

        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Card
            title="What we read"
            body="We look at your inbox for emails about jobs you've applied to and use them to update your dashboard, labels, and tracker. We don't open or look at personal email outside that purpose."
          />
          <Card
            title="What we never touch"
            body="We never archive, delete, or move your messages. The only thing we can change in Gmail is adding our 'assessment' and 'interview' labels — and only to those specific emails."
          />
          <Card
            title="What we send"
            body="We can draft follow-up emails for you using AI, but nothing is sent until you click Send. Auto follow-ups are off by default and you can turn them on or off any time."
          />
          <Card
            title="Where your data goes"
            body="Counts and labels stay on your account. To classify ambiguous emails, we send the subject and a short preview to OpenAI for that single email — never your inbox in bulk, and never the full message body or your contacts."
          />
        </div>

        {err && (
          <p className="mt-4 text-[12.5px] text-rose-700 bg-rose-50/70 rounded-lg px-3 py-2">{err}</p>
        )}

        <div className="mt-6 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2">
          <button
            type="button"
            onClick={deny}
            className="text-[13px] text-slate-500 hover:text-slate-900 px-3 py-2"
          >
            No thanks — sign me out
          </button>
          <button
            type="button"
            onClick={accept}
            disabled={saving}
            className="btn-primary text-[13.5px] disabled:opacity-60"
          >
            {saving ? "Saving…" : "I understand — proceed"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Card({ title, body }) {
  return (
    <div className="rounded-2xl bg-white/70 border border-white/60 px-4 py-3">
      <p className="text-[13px] font-semibold text-slate-900">{title}</p>
      <p className="text-[12.5px] text-slate-600 leading-relaxed mt-1">{body}</p>
    </div>
  );
}
