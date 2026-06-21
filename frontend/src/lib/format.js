// Lightweight formatting helpers (no date-fns dependency).

export function timeAgo(value) {
  if (!value) return "";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.round(months / 12)}y ago`;
}

export function salaryLabel(job) {
  if (job?.salary_lpa) return `₹${job.salary_lpa} LPA`;
  if (job?.salary_raw) return job.salary_raw;
  return null;
}

// "Jia from Unstop <noreply@unstop.com>" → "Jia from Unstop"; bare address → its
// local part prettified.
export function senderName(fromEmail) {
  if (!fromEmail) return "Unknown";
  const m = fromEmail.match(/^\s*"?([^"<]+?)"?\s*</);
  if (m && m[1].trim()) return m[1].trim();
  const addr = fromEmail.replace(/[<>]/g, "").trim();
  const local = addr.split("@")[0] || addr;
  return local.replace(/[._-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function senderAddress(fromEmail) {
  if (!fromEmail) return "";
  const m = fromEmail.match(/<([^>]+)>/);
  return (m ? m[1] : fromEmail).trim();
}
