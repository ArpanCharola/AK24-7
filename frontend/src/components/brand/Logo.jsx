import { useId } from "react";

export const LOGO_VARIANTS = ["ak-tile", "ak", "ak-duo", "ak-italic", "ak-emblem"];
export const LOGO_META = {
  "ak-tile": { name: "AK tile", note: "Compact favicon-style tile" },
  ak: { name: "AK mark", note: "Clean monogram with quiet gradient" },
  "ak-duo": { name: "AK duo", note: "Split-tone monogram" },
  "ak-italic": { name: "AK italic", note: "Forward-leaning motion mark" },
  "ak-emblem": { name: "AK emblem", note: "Primary brand emblem with crisp AI-product chrome" },
};

const DIMS = {
  "ak-tile": { w: 44, h: 44, vb: "0 0 44 44" },
  ak: { w: 44, h: 34, vb: "0 0 44 34" },
  "ak-duo": { w: 44, h: 34, vb: "0 0 44 34" },
  "ak-italic": { w: 46, h: 34, vb: "0 0 46 34" },
  "ak-emblem": { w: 44, h: 44, vb: "0 0 44 44" },
};

const INK = "#0F172A";
const WHITE = "#F8FAFC";
const VIOLET = "#7C3AED";
const BLUE = "#1D4ED8";

function MonoPaths({ stroke, strokeWidth = 3.4, italic = false, splitStroke }) {
  const transform = italic ? "translate(1 0) skewX(-12)" : undefined;
  return (
    <g transform={transform} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeWidth={strokeWidth}>
      <path d="M6 28 L16 6 L26 28" stroke={stroke} />
      <path d="M10.5 18 H21.5" stroke={stroke} />
      <path d="M29 6 V28" stroke={stroke} />
      <path d="M29 17 L39 6" stroke={splitStroke || stroke} />
      <path d="M29 17 L39 28" stroke={splitStroke || stroke} />
    </g>
  );
}

function Emblem({ gradientId }) {
  return (
    <>
      <rect x="3" y="3" width="38" height="38" rx="13" fill={INK} />
      <rect x="3" y="3" width="38" height="38" rx="13" fill="none" stroke={`url(#${gradientId})`} strokeWidth="1.8" />
      <g transform="translate(0 1)">
        <MonoPaths stroke={WHITE} strokeWidth={3.55} splitStroke={`url(#${gradientId})`} />
      </g>
    </>
  );
}

function Tile({ gradientId }) {
  return (
    <>
      <rect x="2.5" y="2.5" width="39" height="39" rx="12.5" fill={INK} />
      <rect x="2.5" y="2.5" width="39" height="39" rx="12.5" fill="none" stroke={`url(#${gradientId})`} strokeWidth="1.5" />
      <g transform="translate(0 0.5)">
        <MonoPaths stroke={WHITE} strokeWidth={3.9} splitStroke={`url(#${gradientId})`} />
      </g>
    </>
  );
}

function Marks({ variant, gradientId, monoId }) {
  if (variant === "ak-tile") return <Tile gradientId={gradientId} />;
  if (variant === "ak-duo") return <MonoPaths stroke={INK} splitStroke={`url(#${gradientId})`} />;
  if (variant === "ak-italic") return <MonoPaths stroke={`url(#${monoId})`} italic />;
  if (variant === "ak-emblem") return <Emblem gradientId={gradientId} />;
  return <MonoPaths stroke={`url(#${monoId})`} />;
}

export default function Logo({ variant = "ak-emblem", size = 36, className = "", ...rest }) {
  const id = useId().replace(/:/g, "");
  const { w, h, vb } = DIMS[variant] || DIMS["ak-emblem"];
  const gradientId = `${id}-brand`;
  const monoId = `${id}-mono`;

  return (
    <svg
      width={(size * w) / h}
      height={size}
      viewBox={vb}
      fill="none"
      className={className}
      role="img"
      aria-label="AK24/7 Jobs"
      {...rest}
    >
      <defs>
        <linearGradient id={gradientId} x1="7" y1="6" x2="37" y2="34" gradientUnits="userSpaceOnUse">
          <stop stopColor={VIOLET} />
          <stop offset="1" stopColor={BLUE} />
        </linearGradient>
        <linearGradient id={monoId} x1="6" y1="5" x2="39" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor={INK} />
          <stop offset="1" stopColor={VIOLET} />
        </linearGradient>
      </defs>
      <Marks variant={variant} gradientId={gradientId} monoId={monoId} />
    </svg>
  );
}

export function Wordmark({ variant: _variant = "ak-emblem", size = 34, tagline = "Jobs in India", className = "" }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <img
        src="/favicon.ico?v=11"
        alt=""
        aria-hidden="true"
        className="brand-favicon"
        style={{ width: size, height: size }}
      />
      <div className="flex flex-col leading-none">
        <span className="text-[18px] font-semibold tracking-[-0.03em] text-slate-950">
          AK<span className="text-brand">24/7</span> Jobs
        </span>
        {tagline && (
          <span className="mt-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {tagline}
          </span>
        )}
      </div>
    </div>
  );
}
