import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import api from "../services/api";

// After "Tailor & Apply", a pendingApply job sits in localStorage. Once the user
// leaves the tailor page (presumably after applying), prompt them to track it.
export default function ApplyPrompt() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [pending, setPending] = useState(null);

  useEffect(() => {
    if (pathname.startsWith("/tailor-resume")) { setPending(null); return; }
    try {
      const raw = localStorage.getItem("pendingApply");
      setPending(raw ? JSON.parse(raw) : null);
    } catch {
      setPending(null);
    }
  }, [pathname]);

  if (!pending) return null;

  function clear() {
    localStorage.removeItem("pendingApply");
    setPending(null);
  }

  async function track() {
    try {
      await api.post("/saved-applications/", {
        company: pending.company || "Unknown company",
        role: pending.role || "Role not specified",
        applied_at: new Date().toISOString(),
        status: "applied",
        job_link: pending.job_link || null,
      });
    } finally {
      clear();
      navigate("/tracker");
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 glass-strong rounded-2xl p-4 w-80 animate-slide-up">
      <button onClick={clear} className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"><X size={14} /></button>
      <p className="text-[13px] font-semibold">Did you apply?</p>
      <p className="text-[12px] text-muted-foreground mt-0.5 truncate">
        {pending.company}{pending.role ? ` — ${pending.role}` : ""}
      </p>
      <div className="flex gap-2 mt-3">
        <button onClick={track} className="btn-primary !py-1.5 !px-3 text-[12px] flex-1">Yes, track it</button>
        <button onClick={clear} className="btn-secondary !py-1.5 !px-3 text-[12px]">Not yet</button>
      </div>
    </div>
  );
}
