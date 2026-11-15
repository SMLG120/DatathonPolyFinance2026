import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "quiet";
type Size = "md" | "sm";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /**
   * Shows the button as unavailable but keeps it focusable and clickable, so a
   * keyboard or screen-reader user can reach it and be told WHY it is not
   * available (the click handler explains). A natively `disabled` button is
   * skipped by the keyboard and explains nothing.
   */
  softDisabled?: boolean;
  /** A request started by this button is in flight. Blocks repeat clicks. */
  busy?: boolean;
  /** Text shown while busy, e.g. "Confirming…". */
  busyLabel?: string;
  icon?: ReactNode;
  iconAfter?: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

const BASE = "inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors text-left";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-on-accent border border-accent hover:bg-accent-strong hover:border-accent-strong",
  secondary: "bg-surface text-accent border border-accent hover:bg-accent-soft",
  quiet: "text-accent underline decoration-1 underline-offset-4 hover:text-accent-strong hover:decoration-2",
};

/**
 * A button that cannot act right now (soft-disabled or busy). It is still
 * focusable and readable, so it keeps AA contrast: grey text on a grey fill
 * with a dashed outline, instead of a faded copy of the active style.
 */
const UNAVAILABLE = "bg-sunken text-ink-muted border border-dashed border-line-strong cursor-default";

const SIZES: Record<Size, string> = {
  md: "min-h-11 px-4 py-2 text-base",
  sm: "min-h-9 px-3 py-1.5 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  softDisabled = false,
  busy = false,
  busyLabel,
  icon,
  iconAfter,
  className,
  children,
  onClick,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(BASE, softDisabled || busy ? UNAVAILABLE : VARIANTS[variant], SIZES[size], variant === "quiet" && "px-1", className)}
      aria-disabled={softDisabled || busy ? true : undefined}
      aria-busy={busy ? true : undefined}
      onClick={(event) => {
        if (busy) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      {...rest}
    >
      {icon}
      <span>{busy && busyLabel ? busyLabel : children}</span>
      {iconAfter}
    </button>
  );
}

export interface LinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  iconAfter?: ReactNode;
}

/** A link that looks like a button. Used for moving between stages: navigation is a link. */
export function LinkButton({ variant = "secondary", size = "md", icon, iconAfter, className, children, ...rest }: LinkButtonProps) {
  return (
    <a className={cn(BASE, VARIANTS[variant], SIZES[size], variant === "quiet" && "px-1", className)} {...rest}>
      {icon}
      <span>{children}</span>
      {iconAfter}
    </a>
  );
}
