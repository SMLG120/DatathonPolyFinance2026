import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ErrorIcon, InfoIcon, UnknownIcon, WarningIcon } from "./icons";

export type NoticeTone = "info" | "caution" | "error" | "unknown";

const TONES: Record<NoticeTone, { box: string; icon: ReactNode }> = {
  info: { box: "bg-accent-soft border-accent text-ink", icon: <InfoIcon className="text-accent" /> },
  caution: { box: "bg-unknown-soft border-unknown text-ink", icon: <WarningIcon className="text-unknown" /> },
  error: { box: "bg-fail-soft border-fail text-ink", icon: <ErrorIcon className="text-fail" /> },
  unknown: { box: "bg-unknown-soft border-unknown border-dashed text-ink", icon: <UnknownIcon className="text-unknown" /> },
};

export interface NoticeProps {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  /**
   * `alert` interrupts a screen reader (errors that need action); `status`
   * waits for a pause (progress and results). Omit for content that is simply
   * part of the page when it loads.
   */
  role?: "alert" | "status";
  className?: string;
  action?: ReactNode;
}

/** An inline message. The title carries the meaning in words; the tint and icon support it. */
export function Notice({ tone = "info", title, children, role, className, action }: NoticeProps) {
  const { box, icon } = TONES[tone];
  return (
    <div role={role} className={cn("flex gap-3 rounded-md border-l-4 px-4 py-3", box, className)}>
      <span className="mt-0.5 flex-none">{icon}</span>
      <div className="min-w-0 flex-1 space-y-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className="space-y-2 text-[0.9375rem]">{children}</div> : null}
        {action ? <div className="pt-2">{action}</div> : null}
      </div>
    </div>
  );
}
