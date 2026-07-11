import { useId } from "react";

/* ─────────────────────────────────────────────────────────────────────────────
   Brand logo system — AK24/7Jobs
   A custom interlocked "AK" monogram: the A's right leg and the K's stem are one
   shared central spine, so the two letters read as a single ownable ligature —
   not set type. Drawn as a bold monoline in the violet -> cyan brand. Each mark
   gets a unique gradient id (useId) so many can coexist on /logo-lab.

   Variants:
     ak-tile    — white monogram on a gradient rounded tile (app icon / favicon)
     ak         — gradient monoline monogram
     ak-duo     — two-tone: violet A spine + cyan K arms
     ak-italic  — forward italic lean (dynamic)
     ak-emblem  — monogram inside a gradient-outlined squircle badge
   ───────────────────────────────────────────────────────────────────────── */

export const LOGO_VARIANTS = ["ak-tile", "ak", "ak-duo", "ak-italic", "ak-emblem"];

export const LOGO_META = {
  "ak-tile": { name: "AK tile", note: "White ligature on gradient — app icon" },
  ak: { name: "AK ligature", note: "Shared-spine monoline" },
  "ak-duo": { name: "AK duo", note: "Violet A · cyan K" },
  "ak-italic": { name: "AK italic", note: "Forward lean — dynamic" },
  "ak-emblem": { name: "AK emblem", note: "Ligature in a badge" },
};

const DIMS = {
  "ak-tile": { w: 40, h: 40, vb: "0 0 40 40" },
  ak: { w: 42, h: 36, vb: "0 0 42 36" },
  "ak-duo": { w: 42, h: 36, vb: "0 0 42 36" },
  "ak-italic": { w: 46, h: 36, vb: "0 0 46 36" },
  "ak-emblem": { w: 44, h: 40, vb: "0 0 44 40" },
};

// Interlocked AK geometry (base coordinate space, ~42x36). The vertical stem is
// shared between the A (left diagonal + crossbar) and the K (two arms).
const AK = {
  aLeg: "M21 5 L5 31",
  spine: "M21 5 L21 31",
  bar: "M10.7 22 L21 22",
  kUp: "M21 17 L37 5",
  kLo: "M21 17 L38 31",
};

// Render the five AK strokes. `a`/`k` let the duo variant tint each letter.
function AkStrokes({ a, k, width = 4 }) {
  const base = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round", strokeWidth: width };
  return (
    <>
      <path d={AK.aLeg} stroke={a} {...base} />
      <path d={AK.spine} stroke={a} {...base} />
      <path d={AK.bar} stroke={a} {...base} />
      <path d={AK.kUp} stroke={k} {...base} />
      <path d={AK.kLo} stroke={k} {...base} />
    </>
  );
}

function Marks({ variant, gid }) {
  const g = `url(#${gid})`;
  switch (variant) {
    case "ak-tile":
      return (
        <>
          <rect x="0" y="0" width="40" height="40" rx="11" fill={g} />
          <g transform="translate(4.5 6.5) scale(0.74)">
            <AkStrokes a="#fff" k="#fff" width={5} />
          </g>
        </>
      );
    case "ak":
      return <AkStrokes a={g} k={g} />;
    case "ak-duo":
      return <AkStrokes a="hsl(var(--brand))" k="hsl(var(--brand-2))" />;
    case "ak-italic":
      return (
        <g transform="translate(5 0) skewX(-10)">
          <AkStrokes a={g} k={g} />
        </g>
      );
    case "ak-emblem":
      return (
        <>
          <rect x="2" y="2" width="40" height="36" rx="12" fill="none" stroke={g} strokeWidth="2.4" />
          <g transform="translate(8 7) scale(0.62)">
            <AkStrokes a={g} k={g} width={5} />
          </g>
        </>
      );
    default:
      return null;
  }
}

/**
 * Brand mark. `size` is the rendered height; width follows the variant aspect.
 */
export default function Logo({ variant = "ak-tile", size = 36, className = "", ...rest }) {
  const gid = useId().replace(/:/g, "") + "-" + variant;
  const { w, h, vb } = DIMS[variant] || DIMS["ak-tile"];
  return (
    <svg
      width={(size * w) / h}
      height={size}
      viewBox={vb}
      fill="none"
      className={className}
      role="img"
      aria-label="AK24/7Jobs"
      {...rest}
    >
      <defs>
        <linearGradient id={gid} x1="2" y1="4" x2="40" y2="36" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0F5B45" />
          <stop offset="1" stopColor="#B8862E" />
        </linearGradient>
      </defs>
      <Marks variant={variant} gid={gid} />
    </svg>
  );
}

/**
 * Logo lockup: mark + "AK24/7Jobs" wordmark (with "24/7" gradient-accented) and
 * an optional tagline. Text follows the theme via --foreground.
 */
export function Wordmark({ variant = "ak-tile", size = 34, tagline = "Jobs in India", className = "" }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <Logo variant={variant} size={size} />
      <div className="flex flex-col leading-tight">
        <span className="font-display text-[18px] font-semibold italic tracking-tight text-foreground">
          AK<span className="text-brand-gradient">24/7</span> Jobs
        </span>
        {tagline && (
          <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-semibold">
            {tagline}
          </span>
        )}
      </div>
    </div>
  );
}
