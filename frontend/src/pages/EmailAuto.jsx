import { useState, useEffect, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { emailApi } from "../services/api";
import EmailSidebar from "../components/Email/EmailSidebar";
import EmailList from "../components/Email/EmailList";
import EmailDetail from "../components/Email/EmailDetail";
import ComposeModal from "../components/Email/ComposeModal";

export default function EmailAuto() {
  const qc = useQueryClient();
  const [folder, setFolder] = useState("INBOX");
  const [selected, setSelected] = useState(null);
  const [composing, setComposing] = useState(false);

  const [messages, setMessages] = useState([]);
  const [pageToken, setPageToken] = useState(null);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["email-status"],
    queryFn: () => emailApi.status().then((r) => r.data),
  });

  const { data: labelsData } = useQuery({
    queryKey: ["email-labels"],
    queryFn: () => emailApi.labels().then((r) => r.data),
    enabled: !!status?.connected,
  });
  const userLabels = (labelsData?.labels || []).filter((l) => l.type === "user");

  const loadPage = useCallback(async (reset) => {
    setLoadingMsgs(true);
    try {
      let next = null;
      let batch = [];
      if (folder.startsWith("label:")) {
        const labelId = folder.slice("label:".length);
        batch = (await emailApi.labelMessages(labelId, 50)).data || [];
      } else {
        const { data } = await emailApi.inbox({ label: folder, limit: 50, pageToken: reset ? null : pageToken });
        batch = data.messages || [];
        next = data.next_page_token || null;
      }
      setPageToken(next);
      setMessages((cur) => (reset ? batch : [...cur, ...batch]));
    } catch {
      if (reset) setMessages([]);
    } finally {
      setLoadingMsgs(false);
    }
  }, [folder, pageToken]);

  // Reload when the folder changes (and once connected).
  useEffect(() => {
    if (!status?.connected) return;
    setSelected(null);
    setMessages([]);
    setPageToken(null);
    loadPage(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folder, status?.connected]);

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["email-detail", selected?.id],
    queryFn: () => emailApi.message(selected.id).then((r) => r.data),
    enabled: !!selected,
  });

  function connectGmail() {
    emailApi.connect().then((r) => { if (r.data?.auth_url) window.location.href = r.data.auth_url; });
  }

  if (statusLoading) {
    return <div className="flex items-center justify-center h-full text-[13px] text-muted-foreground">Loading…</div>;
  }

  if (!status?.connected) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-6">
        <Mail size={44} strokeWidth={1} className="text-muted-foreground/40 mb-3" />
        <h2 className="text-base font-semibold">Connect Gmail</h2>
        <p className="text-[13px] text-muted-foreground mt-1 max-w-sm">
          Read your inbox, auto-tag job emails, and reply with AI — all inside AK24/7.
        </p>
        <button onClick={connectGmail} className="btn-primary mt-4 text-[13px]">Connect Gmail</button>
        {status?.oauth_configured === false && (
          <p className="text-[11.5px] text-warning mt-3">Google OAuth isn't configured on the server yet.</p>
        )}
      </div>
    );
  }

  const folderTitle = folder.startsWith("label:")
    ? (userLabels.find((l) => `label:${l.id}` === folder)?.name || "Label")
    : folder.toLowerCase();

  return (
    <div className="flex h-full overflow-hidden">
      <EmailSidebar
        active={folder}
        onSelect={setFolder}
        userLabels={userLabels}
        onCompose={() => setComposing(true)}
        onLabelCreated={() => qc.invalidateQueries({ queryKey: ["email-labels"] })}
      />

      {/* List */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <div className="px-4 py-2.5 border-b border-border shrink-0">
          <h2 className="text-[13px] font-semibold capitalize">{folderTitle}</h2>
        </div>
        <div className="flex-1 overflow-y-auto">
          <EmailList messages={messages} activeId={selected?.id} onSelect={setSelected} loading={loadingMsgs && messages.length === 0} />
          {pageToken && !folder.startsWith("label:") && (
            <div className="p-3 text-center">
              <button onClick={() => loadPage(false)} disabled={loadingMsgs} className="btn-secondary !py-1.5 !px-4 text-[12px]">
                {loadingMsgs ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Detail */}
      {selected && (
        <div className="w-[460px] shrink-0 overflow-hidden">
          {detailLoading ? (
            <div className="flex items-center justify-center h-full text-[13px] text-muted-foreground border-l border-border">Loading…</div>
          ) : (
            <EmailDetail
              message={detail || selected}
              onClose={() => setSelected(null)}
              onAddedToTracker={() => qc.invalidateQueries({ queryKey: ["saved-applications"] })}
            />
          )}
        </div>
      )}

      {composing && <ComposeModal onClose={() => setComposing(false)} />}
    </div>
  );
}
