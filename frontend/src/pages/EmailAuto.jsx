import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { emailApi } from "../services/api";
import EmailSidebar from "../components/Email/EmailSidebar";
import EmailList from "../components/Email/EmailList";
import EmailDetail from "../components/Email/EmailDetail";
import ComposeModal from "../components/Email/ComposeModal";

const MOBILE_FOLDERS = [
  ["INBOX", "Inbox"], ["STARRED", "Starred"], ["SENT", "Sent"],
  ["DRAFT", "Drafts"], ["IMPORTANT", "Important"], ["SPAM", "Spam"],
];

export default function EmailAuto() {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState("INBOX");
  const [selected, setSelected] = useState(null);
  const [composing, setComposing] = useState(false);
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

  const loadPage = useCallback(async (reset) => {
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
      if (reset) setMessages([]);
    } finally {
      setLoadingMsgs(false);
    }
  }, [folder, pageToken]);

  useEffect(() => {
    if (!status?.connected) return;
    setSelected(null);
    setMessages([]);
    setPageToken(null);
    loadPage(true);
    // loadPage intentionally re-fetches when folder changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder, status?.connected]);

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
      <div className="flex h-full flex-col items-center justify-center p-6 text-center">
        <Mail size={44} strokeWidth={1} className="mb-3 text-muted-foreground/40" />
        <h2 className="text-base font-semibold">Connect Gmail</h2>
        <p className="mt-1 max-w-sm text-[13px] text-muted-foreground">Read your inbox, auto-tag job emails, and reply with AI — all inside AK24/7.</p>
        <button onClick={connectGmail} className="btn-primary mt-4 text-[13px]">Connect Gmail</button>
        {status?.oauth_configured === false && <p className="mt-3 text-[11.5px] text-warning">Google OAuth isn't configured on the server yet.</p>}
      </div>
    );
  }

  const folderTitle = folder.startsWith("label:")
    ? (userLabels.find((label) => `label:${label.id}` === folder)?.name || "Label")
    : folder.toLowerCase();

  return (
    <div className="email-workspace relative flex min-h-0 flex-1 overflow-hidden bg-card">
      <EmailSidebar
        active={folder}
        onSelect={setFolder}
        userLabels={userLabels}
        onCompose={() => setComposing(true)}
        onLabelCreated={() => queryClient.invalidateQueries({ queryKey: ["email-labels"] })}
      />

      <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 border-b border-border bg-card px-3 py-2 lg:hidden">
        <label className="sr-only" htmlFor="email-folder">Mailbox folder</label>
        <select id="email-folder" value={folder} onChange={(event) => setFolder(event.target.value)} className="input-glass !w-auto !py-1.5 text-[12px] capitalize">
          {MOBILE_FOLDERS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          {userLabels.map((label) => <option key={label.id} value={`label:${label.id}`}>{label.name}</option>)}
        </select>
        <button onClick={() => setComposing(true)} className="btn-primary ml-auto !px-3 !py-1.5 text-[12px]">Compose</button>
      </div>

      <section className={`${selected ? "hidden lg:flex lg:w-[42%] xl:w-[40%]" : "flex flex-1"} min-w-0 flex-col overflow-hidden pt-[52px] lg:pt-0 lg:border-r lg:border-border`} aria-label="Message list">
        <header className="shrink-0 border-b border-border px-4 py-3">
          <h2 className="text-[14px] font-semibold capitalize">{folderTitle}</h2>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <EmailList messages={messages} activeId={selected?.id} onSelect={setSelected} loading={loadingMsgs && messages.length === 0} />
          {pageToken && !folder.startsWith("label:") && (
            <div className="p-3 text-center">
              <button onClick={() => loadPage(false)} disabled={loadingMsgs} className="btn-secondary !px-4 !py-1.5 text-[12px]">
                {loadingMsgs ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      </section>

      {selected && (
        <div className="flex min-w-0 flex-1 overflow-hidden pt-[52px] lg:pt-0">
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
      )}

      {composing && <ComposeModal onClose={() => setComposing(false)} />}
    </div>
  );
}
