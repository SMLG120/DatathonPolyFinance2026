import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";
import { Button } from "./Button";
import { ClockIcon } from "./icons";
import { Notice } from "./Notice";

/**
 * The four states every asynchronous area can be in besides "ready":
 * loading, empty, unknown data and execution error. Using these everywhere
 * keeps the wording and the announcements consistent.
 */

/** Something is being fetched or calculated. Announced politely; no spinner animation. */
export function LoadingBlock({ label, className }: { label: string; className?: string }) {
  return (
    <div
      role="status"
      className={cn("flex items-center gap-3 rounded-md border border-dashed border-line-strong bg-surface px-4 py-3 text-ink-muted", className)}
    >
      <ClockIcon className="flex-none" />
      <span>{label}</span>
    </div>
  );
}

/** Nothing to show yet, with the reason and usually the way forward. */
export function EmptyBlock({ title, children, action, className }: { title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-md border border-dashed border-line-strong bg-surface px-4 py-5", className)}>
      <p className="font-semibold text-ink">{title}</p>
      {children ? <div className="mt-1 max-w-prose text-ink-muted">{children}</div> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

/** A request failed. Says what failed, that nothing was changed, and offers a retry. */
export function ErrorBlock({
  title,
  message,
  onRetry,
  retryLabel = "Try again",
  className,
  children,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <Notice
      tone="error"
      role="alert"
      title={title}
      className={className}
      action={
        onRetry ? (
          <Button size="sm" onClick={onRetry}>
            {t(retryLabel)}
          </Button>
        ) : undefined
      }
    >
      <p>{message}</p>
      {children}
    </Notice>
  );
}

/** Data that should exist is missing. Never rendered as a zero or a pass. */
export function UnknownBlock({ title, children, className }: { title: string; children?: ReactNode; className?: string }) {
  return (
    <Notice tone="unknown" title={title} className={className}>
      {children}
    </Notice>
  );
}
