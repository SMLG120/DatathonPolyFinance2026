import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { buttonVariants } from "@/components/shadcn/button-variants";
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

/**
 * A button that cannot act right now (soft-disabled or busy). It is still
 * focusable and readable, so it keeps AA contrast: grey text on a grey fill
 * with a dashed outline, instead of a faded copy of the active style.
 */
const UNAVAILABLE = "bg-sunken text-ink-muted border border-dashed border-line-strong cursor-default";

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
      data-slot="button"
      type={type}
      className={cn(buttonVariants({ variant, size }), (softDisabled || busy) && UNAVAILABLE, className)}
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
    <a className={cn(buttonVariants({ variant, size }), className)} {...rest}>
      {icon}
      <span>{children}</span>
      {iconAfter}
    </a>
  );
}
