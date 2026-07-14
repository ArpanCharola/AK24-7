import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, Sparkles } from "lucide-react";
import { emailApi } from "../services/api";
import EmailSidebar from "../components/Email/EmailSidebar";
import EmailList from "../components/Email/EmailList";
import EmailDetail from "../components/Email/EmailDetail";

const MOBILE_FOLDERS = [
  ["INBOX", "Inbox"],
  ["STARRED", "Starred"],
  ["SENT", "Sent"],
  ["DRAFT", "Drafts"],
  ["IMPORTANT", "Important"],
  ["SPAM", "Spam"],
];

export default function EmailAuto() {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState("INBOX");
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [pageToken, setPageToken] = useState(null);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["email-status"],
    queryFn: () => emailApi.status().then((response) => response.data),
  });
  const { data: labelsData } = useQuery({
    queryKey: ["email-labels"],
    queryFn: () => emailApi.labels().then((response) => response.data),
    enabled: !!status?.connected,
  });
  const userLabels = (labelsData?.labels || []).filter((label) => label.type === "user");

  const loadPage = useCallback(
    async (reset) => {
      setLoadingMsgs(true);
      try {
        let next = null;
        let batch = [];
        if (folder.startsWith("label:")) {
          batch = (await emailApi.labelMessages(folder.slice("label:".length), 50)).data || [];
        } else {
          const { data } = await emailApi.inbox({ label: folder, limit: 50, pageToken: reset ? null : pageToken });
          batch = data.messages || [];
          next = data.next_page_token || null;
        }
        setPageToken(next);
        setMessages((current) => (reset ? batch : [...current, ...batch]));
      } catch {
        if (reset) {
          setMessages([]);
          setSelected(null);
        }
      } finally {
        setLoadingMsgs(false);
      }
    },
    [folder, pageToken]
  );

  useEffect(() => {
    if (!status?.connected) return;
    setSelected(null);
    setMessages([]);
    setPageToken(null);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder, status?.connected]);

  useEffect(() => {
    if (!messages.length) {
      if (selected) setSelected(null);
      return;
    }

    if (!selected) {
      setSelected(messages[0]);
      return;
    }

    const updatedSelection = messages.find((message) => message.id === selected.id);
    if (!updatedSelection) {
      setSelected(messages[0]);
    } else if (updatedSelection !== selected) {
      setSelected(updatedSelection);
    }
  }, [messages, selected]);

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["email-detail", selected?.id],
    queryFn: () => emailApi.message(selected.id).then((response) => response.data),
    enabled: !!selected,
  });

  function connectGmail() {
    emailApi.connect().then((response) => {
      if (response.data?.auth_url) window.location.href = response.data.auth_url;
    });
  }

  if (statusLoading) {
    return <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground">Loading…</div>;
  }

  if (!status?.connected) {
    return (
      <div className="mx-auto flex h-full w-full max-w-4xl flex-col items-center justify-center px-6 py-12 text-center">
        <div className="glass-strong w-full max-w-2xl rounded-[32px] px-8 py-12">
          <span className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-[20px] bg-brand/10 text-brand">
            <Mail size={28} strokeWidth={1.5} />
          </span>
          <h2 className="text-2xl font-semibold text-foreground">Connect Gmail</h2>
          <p className="mx-auto mt-3 max-w-xl text-[14px] leading-7 text-muted-foreground">
            Read recruiter updates, auto-tag application mail, and push interesting threads into your tracker.
          </p>
          <button onClick={connectGmail} className="btn-gradient mt-6 !rounded-full !px-5 !py-3 text-[13px]">
            <Sparkles size={14} /> Connect Gmail
          </button>
          {status?.oauth_configured === false && (
            <p className="mt-4 text-[11.5px] text-warning">Google OAuth isn't configured on the server yet.</p>
          )}
        </div>
      </div>
    );
  }

  const folderTitle = folder.startsWith("label:")
    ? userLabels.find((label) => `label:${label.id}` === folder)?.name || "Label"
    : folder.toLowerCase();

  return (
    <div className="mx-auto flex w-full max-w-[1560px] flex-1 flex-col gap-5 px-5 py-6 md:px-8">
      <section className="rounded-[32px] border border-white/10 bg-[linear-gradient(135deg,#0f2ea8_0%,#253dce_52%,#6d28d9_140%)] px-6 py-7 text-white shadow-[0_30px_90px_-46px_rgba(37,61,206,0.52)] md:px-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <span className="inline-flex rounded-full border border-white/14 bg-white/8 px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-white/82">Recruiter inbox</span>
            <h1 className="mt-3 text-[clamp(2rem,4vw,3.5rem)] font-semibold leading-[1.02] tracking-tight text-white">
              Keep recruiter email inside the same flow as your applications.
            </h1>
            <p className="mt-3 text-[14px] leading-7 text-slate-100/84">
              Browse recruiter and application mails in one place.
            </p>
          </div>
        </div>
      </section>

      <section className="email-workspace flex min-h-[72vh] flex-col overflow-hidden rounded-[30px] border border-border/80 bg-card/85 shadow-[0_20px_60px_-40px_hsl(var(--brand)/0.24)] backdrop-blur-sm lg:flex-row">
        <EmailSidebar
          active={folder}
          onSelect={setFolder}
          userLabels={userLabels}
          onLabelCreated={() => queryClient.invalidateQueries({ queryKey: ["email-labels"] })}
        />

        <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 border-b border-border bg-card/95 px-3 py-2 backdrop-blur-sm lg:hidden">
          <label className="sr-only" htmlFor="email-folder">
            Mailbox folder
          </label>
          <select id="email-folder" value={folder} onChange={(event) => setFolder(event.target.value)} className="input-glass !w-auto !py-1.5 text-[12px] capitalize">
            {MOBILE_FOLDERS.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
            {userLabels.map((label) => (
              <option key={label.id} value={`label:${label.id}`}>
                {label.name}
              </option>
            ))}
          </select>
        </div>

        <section className={`${selected ? "hidden lg:flex" : "flex flex-1"} min-w-0 flex-col overflow-hidden pt-[52px] lg:w-[32%] lg:min-w-[340px] lg:max-w-[420px] lg:flex lg:pt-0 lg:border-r lg:border-border xl:w-[30%]`} aria-label="Message list">
          <header className="shrink-0 border-b border-border px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-[14px] font-semibold capitalize text-foreground">{folderTitle}</h2>
                <p className="mt-1 text-[11.5px] text-muted-foreground">Recent recruiter and application signals</p>
              </div>
              <span className="rounded-full border border-border bg-muted/35 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {messages.length} items
              </span>
            </div>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto bg-card/65">
            <EmailList messages={messages} activeId={selected?.id} onSelect={setSelected} loading={loadingMsgs && messages.length === 0} />
            {pageToken && !folder.startsWith("label:") && (
              <div className="p-3 text-center">
                <button onClick={() => loadPage(false)} disabled={loadingMsgs} className="btn-secondary !rounded-full !px-4 !py-1.5 text-[12px]">
                  {loadingMsgs ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        </section>

        {selected ? (
          <div className="flex min-w-0 flex-1 overflow-hidden pt-[52px] lg:basis-0 lg:pt-0 lg:min-w-[560px]">
            {detailLoading ? (
              <div className="flex h-full flex-1 items-center justify-center text-[13px] text-muted-foreground">Loading…</div>
            ) : (
              <EmailDetail
                message={detail || selected}
                onClose={() => setSelected(null)}
                onAddedToTracker={() => queryClient.invalidateQueries({ queryKey: ["saved-applications"] })}
              />
            )}
          </div>
        ) : (
          <div className="hidden flex-1 items-center justify-center lg:flex">
            <div className="max-w-md text-center">
              <span className="mx-auto mb-4 inline-flex h-14 w-14 items-center justify-center rounded-[20px] bg-brand/10 text-brand">
                <Mail size={26} strokeWidth={1.5} />
              </span>
              <h3 className="text-lg font-semibold text-foreground">Open a thread to read</h3>
              <p className="mt-2 text-[13px] leading-6 text-muted-foreground">
                Select any message to open the reader or add the conversation to your job tracker.
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
