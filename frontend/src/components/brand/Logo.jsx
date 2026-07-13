import { useId } from "react";

export const LOGO_VARIANTS = ["ak-tile", "ak", "ak-duo", "ak-italic", "ak-emblem"];
export const LOGO_META = {
  "ak-tile": { name: "AK tile", note: "Navy app mark with an emerald detail" },
  ak: { name: "AK mark", note: "Clean shared-spine monogram" },
  "ak-duo": { name: "AK duo", note: "Navy A and emerald K" },
  "ak-italic": { name: "AK italic", note: "Forward-leaning monogram" },
  "ak-emblem": { name: "AK emblem", note: "Monogram in a navy badge" },
};

const DIMS = {
  "ak-tile": { w: 40, h: 40, vb: "0 0 40 40" }, ak: { w: 42, h: 36, vb: "0 0 42 36" },
  "ak-duo": { w: 42, h: 36, vb: "0 0 42 36" }, "ak-italic": { w: 46, h: 36, vb: "0 0 46 36" },
  "ak-emblem": { w: 44, h: 40, vb: "0 0 44 40" },
};
const AK = { aLeg: "M21 5 L5 31", spine: "M21 5 L21 31", bar: "M10.7 22 L21 22", kUp: "M21 17 L37 5", kLo: "M21 17 L38 31" };
const NAVY = "#14243D";
const EMERALD = "#14956F";

function AkStrokes({ a, k, width = 4 }) {
  const base = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: width };
  return <><path d={AK.aLeg} stroke={a} {...base} /><path d={AK.spine} stroke={a} {...base} /><path d={AK.bar} stroke={a} {...base} /><path d={AK.kUp} stroke={k} {...base} /><path d={AK.kLo} stroke={k} {...base} /></>;
}

function Marks({ variant, gradient }) {
  if (variant === "ak-tile") return <><rect width="40" height="40" rx="11" fill={NAVY} /><g transform="translate(4.5 6.5) scale(0.74)"><AkStrokes a="#F7FAFC" k="#6FE0B6" width={5} /></g></>;
  if (variant === "ak-duo") return <AkStrokes a={NAVY} k={EMERALD} />;
  if (variant === "ak-italic") return <g transform="translate(5 0) skewX(-10)"><AkStrokes a={gradient} k={gradient} /></g>;
  if (variant === "ak-emblem") return <><rect x="2" y="2" width="40" height="36" rx="12" fill="none" stroke={NAVY} strokeWidth="2.4" /><g transform="translate(8 7) scale(0.62)"><AkStrokes a={NAVY} k={EMERALD} width={5} /></g></>;
  return <AkStrokes a={gradient} k={gradient} />;
}

export default function Logo({ variant = "ak-tile", size = 36, className = "", ...rest }) {
  const id = useId().replace(/:/g, "");
  const { w, h, vb } = DIMS[variant] || DIMS["ak-tile"];
  const gradient = `url(#${id})`;
  return <svg width={(size * w) / h} height={size} viewBox={vb} fill="none" className={className} role="img" aria-label="AK24/7 Jobs" {...rest}>
    <defs><linearGradient id={id} x1="4" y1="4" x2="38" y2="32" gradientUnits="userSpaceOnUse"><stop stopColor={NAVY} /><stop offset="1" stopColor={EMERALD} /></linearGradient></defs>
    <Marks variant={variant} gradient={gradient} />
  </svg>;
}

export function Wordmark({ variant = "ak-tile", size = 34, tagline = "Jobs in India", className = "" }) {
  return <div className={`flex items-center gap-2.5 ${className}`}><Logo variant={variant} size={size} /><div className="flex flex-col leading-tight"><span className="font-display text-[18px] font-semibold tracking-tight text-foreground">AK<span className="text-brand">24/7</span> Jobs</span>{tagline && <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{tagline}</span>}</div></div>;
}
