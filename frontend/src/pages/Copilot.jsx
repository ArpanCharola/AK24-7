import { useEffect, useRef, useState } from "react";
import { useCopilotChat } from "../hooks/useCopilot";

const SUGGESTIONS = [
  { label: "Break down my fit", text: "Break down how well I fit this role and what would make me a stronger candidate." },
  { label: "Interview prep", text: "Give me a focused interview prep plan for this role based on my profile." },
  { label: "Resume advice", text: "What should I change on my resume to land more interviews for roles like this?" },
  { label: "Close my skill gaps", text: "What are my biggest skill gaps for this role and how do I close them quickly?" },
];

function Avatar({ role }) {
  const isUser = role === "user";
  return (
    <div
      className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 ${isUser ? "bg-slate-200" : ""}`}
      style={!isUser ? { background: "hsl(var(--primary))" } : undefined}
    >
      {isUser ? (
        <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ) : (
        <svg className="w-4 h-4" style={{ color: "hsl(var(--primary-foreground))" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )}
    </div>
  );
}

export default function Copilot() {
  const jobId = new URLSearchParams(window.location.search).get("job_id");
  const [messages, setMessages] = useState([]); // { role, content }
  const [input, setInput] = useState("");
  const { mutateAsync, isPending } = useCopilotChat();
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isPending]);

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || isPending) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content }]);
    setInput("");
    try {
      const res = await mutateAsync({
        message: content,
        history,
        ...(jobId ? { job_id: Number(jobId) } : {}),
      });
      const reply = res?.reply || res?.message || res?.content || "";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: reply || "I couldn't generate a response just now." },
      ]);
    } catch (err) {
      const offline = err?.response?.status === 404;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: offline
            ? "Orion isn't connected yet — the copilot service is still being set up. Try again shortly."
            : err?.response?.data?.detail || "Something went wrong reaching Orion. Please try again.",
        },
      ]);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    send();
  }

  const empty = messages.length === 0;

  return (
    <div className="flex flex-col h-full glass rounded-3xl overflow-hidden animate-fade-in">
      {/* Header */}
      <header className="flex-shrink-0 px-6 py-5 border-b border-white/40 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: "hsl(var(--primary))" }}>
          <svg className="w-5 h-5" style={{ color: "hsl(var(--primary-foreground))" }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-[20px] font-bold text-slate-900 tracking-tight">Orion</h1>
          <p className="text-[12.5px] text-slate-500">
            Your AI career copilot
            {jobId && <span className="ml-1 text-accent-600 font-medium">· focused on a selected job</span>}
          </p>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-3xl mx-auto">
          {empty ? (
            <div className="flex flex-col items-center justify-center text-center py-12">
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4" style={{ background: "hsl(var(--muted))" }}>
                <svg className="w-7 h-7 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.5C3.5 15.3 3 13.7 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-[15px] font-semibold text-slate-800">How can Orion help today?</p>
              <p className="text-[12.5px] text-slate-400 mt-1 max-w-sm">
                Ask about your fit for a role, interview prep, resume improvements, or closing skill gaps.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-2 mt-5 max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => send(s.text)}
                    className="px-3.5 py-2 rounded-xl text-[12.5px] font-medium glass-subtle text-slate-600 hover:text-slate-900 hover:bg-white/70 transition-all"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              {messages.map((m, i) => (
                <div key={i} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                  <Avatar role={m.role} />
                  <div
                    className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-[13px] leading-relaxed whitespace-pre-wrap ${
                      m.role === "user"
                        ? "bg-accent-600 text-white rounded-tr-sm"
                        : "glass-subtle text-slate-700 rounded-tl-sm"
                    }`}
                    style={m.role === "user" ? { background: "hsl(var(--primary))", color: "hsl(var(--primary-foreground))" } : undefined}
                  >
                    {m.content}
                  </div>
                </div>
              ))}
              {isPending && (
                <div className="flex gap-3">
                  <Avatar role="assistant" />
                  <div className="glass-subtle rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
                    {[0, 150, 300].map((d) => (
                      <span
                        key={d}
                        className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce"
                        style={{ animationDelay: `${d}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="flex-shrink-0 border-t border-white/40 px-6 py-4">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
            placeholder="Ask Orion anything about your job search…"
            className="flex-1 resize-none input-glass !py-2.5 max-h-32"
          />
          <button type="submit" disabled={isPending || !input.trim()} className="btn-primary flex-shrink-0 !px-4 !py-2.5">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
