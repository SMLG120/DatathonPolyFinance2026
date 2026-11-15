import type { SVGProps } from "react";

/**
 * Small inline icons. All are decorative: every icon is rendered next to a
 * word that carries the meaning, so they are hidden from assistive technology.
 *
 * The three status icons differ in SHAPE (circle, octagon, diamond) as well as
 * in glyph, so a status can be told apart without colour.
 */
type IconProps = Omit<SVGProps<SVGSVGElement>, "children"> & { size?: number };

function Svg({ size = 20, children, ...props }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

const GLYPH = {
  fill: "none",
  stroke: "var(--color-surface)",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

/** Circle with a check mark. */
export function PassIcon(props: IconProps) {
  return (
    <Svg data-shape="circle" {...props}>
      <circle cx="10" cy="10" r="9" fill="currentColor" />
      <path d="M5.8 10.4l2.8 2.8 5.6-6" {...GLYPH} />
    </Svg>
  );
}

/** Octagon with a cross. */
export function FailIcon(props: IconProps) {
  return (
    <Svg data-shape="octagon" {...props}>
      <path d="M6.3 1h7.4L19 6.3v7.4L13.7 19H6.3L1 13.7V6.3z" fill="currentColor" />
      <path d="M6.8 6.8l6.4 6.4M13.2 6.8l-6.4 6.4" {...GLYPH} />
    </Svg>
  );
}

/** Diamond with a question mark. */
export function UnknownIcon(props: IconProps) {
  return (
    <Svg data-shape="diamond" {...props}>
      <path d="M10 0.6L19.4 10 10 19.4 0.6 10z" fill="currentColor" />
      <path d="M7.9 8.1a2.1 2.1 0 1 1 3.2 1.8c-.7.4-1.1.8-1.1 1.6" {...GLYPH} />
      <circle cx="10" cy="14.2" r="1.1" fill="var(--color-surface)" />
    </Svg>
  );
}

const LINE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="10" r="8" {...LINE} />
      <path d="M10 9v5" {...LINE} />
      <circle cx="10" cy="6.2" r="1" fill="currentColor" />
    </Svg>
  );
}

export function WarningIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10 2.5l8 14H2z" {...LINE} />
      <path d="M10 8v4" {...LINE} />
      <circle cx="10" cy="14.3" r="1" fill="currentColor" />
    </Svg>
  );
}

export function ErrorIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6.6 2h6.8L18 6.6v6.8L13.4 18H6.6L2 13.4V6.6z" {...LINE} />
      <path d="M10 6v5" {...LINE} />
      <circle cx="10" cy="13.8" r="1" fill="currentColor" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 10.5l4 4 8-9" {...LINE} strokeWidth={2} />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 5l10 10M15 5L5 15" {...LINE} strokeWidth={2} />
    </Svg>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 10h12M11 5l5 5-5 5" {...LINE} />
    </Svg>
  );
}

/** Points right while closed; the stylesheet turns it down when its <details> is open. */
export function ChevronIcon({ className, ...props }: IconProps) {
  return (
    <Svg className={className ? `byb-chevron ${className}` : "byb-chevron"} {...props}>
      <path d="M7 4l6 6-6 6" {...LINE} strokeWidth={2} />
    </Svg>
  );
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M16 10H4M9 5l-5 5 5 5" {...LINE} />
    </Svg>
  );
}

/** A page with lines: "open the evidence behind this figure". */
export function EvidenceIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 2.5h7l3.5 3.5v11.5h-10.5z" {...LINE} />
      <path d="M12 2.5V6h3.5M7.5 10h5M7.5 13h5" {...LINE} />
    </Svg>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="10" r="8" {...LINE} />
      <path d="M10 5.5V10l3 2" {...LINE} />
    </Svg>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="4" y="9" width="12" height="8.5" rx="1.5" {...LINE} />
      <path d="M6.5 9V6.5a3.5 3.5 0 0 1 7 0V9" {...LINE} />
    </Svg>
  );
}

export function PersonIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="6.5" r="3.5" {...LINE} />
      <path d="M3 17.5c.8-3.3 3.6-5 7-5s6.2 1.700 7 5" {...LINE} />
    </Svg>
  );
}

/** A hollow circle: "not started / proposed". */
export function HollowCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="10" r="7" {...LINE} strokeDasharray="3 2.5" />
    </Svg>
  );
}

/** A circle crossed out: "superseded / no longer in force". */
export function SupersededIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="10" cy="10" r="7.5" {...LINE} />
      <path d="M4.8 15.2L15.2 4.8" {...LINE} />
    </Svg>
  );
}
