import { Link } from "react-router-dom";
import { AlertCircle } from "lucide-react";

// Shown on /jobs when the profile is missing required fields.
// `completed` is the count of the 5 required fields filled.
export default function ProfileGate({ completed, required = 5 }) {
  if (completed >= required) return null;
  return (
    <div className="flex items-center gap-3 px-4 py-3 mb-4 rounded-xl border border-warning/40 bg-warning/10 text-warning">
      <AlertCircle size={18} strokeWidth={1.75} className="shrink-0" />
      <p className="text-[13px] flex-1">
        Complete your profile before searching for jobs.{" "}
        <span className="font-semibold">{completed}/{required} required fields done.</span>
      </p>
      <Link
        to="/profile"
        className="shrink-0 px-3 py-1.5 text-[12px] font-semibold rounded-lg bg-warning text-white hover:opacity-90 transition-opacity"
      >
        Complete Profile →
      </Link>
    </div>
  );
}
