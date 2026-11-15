import type { ReactNode } from "react";
import type { CoverageStatus, InvestigationStatus, RuleLifecycleStatus, VerdictStatus } from "@/lib/contracts";
import { cn } from "@/lib/cn";
import { ruleStatusLabel } from "@/lib/rules";
import { coverageText, jobStatusText, statusText } from "@/lib/verdict";
import {
  CheckIcon,
  ClockIcon,
  ErrorIcon,
  FailIcon,
  HollowCircleIcon,
  InfoIcon,
  PassIcon,
  SupersededIcon,
  UnknownIcon,
  WarningIcon,
} from "./icons";

export type BadgeTone = "neutral" | "accent" | "pass" | "fail" | "unknown";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-sunken text-ink border-line-strong",
  accent: "bg-accent-soft text-accent-strong border-accent",
  pass: "bg-pass-soft text-pass border-pass",
  fail: "bg-fail-soft text-fail border-fail",
  unknown: "bg-unknown-soft text-unknown border-unknown",
};

export interface BadgeProps {
  tone?: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Dashed outline: used for anything provisional (proposed, unknown, unverified). */
  dashed?: boolean;
}

/** A short label. Meaning is always in the words; tone and icon only support it. */
export function Badge({ tone = "neutral", icon, children, className, dashed = false }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-sm font-semibold leading-6",
        dashed && "border-dashed",
        TONES[tone],
        className,
      )}
    >
      {icon}
      <span>{children}</span>
    </span>
  );
}

const VERDICT: Record<VerdictStatus, { tone: BadgeTone; Icon: typeof PassIcon; dashed: boolean }> = {
  PASS: { tone: "pass", Icon: PassIcon, dashed: false },
  FAIL: { tone: "fail", Icon: FailIcon, dashed: false },
  UNKNOWN: { tone: "unknown", Icon: UnknownIcon, dashed: true },
};

/**
 * PASS / FAIL / UNKNOWN as a word, an icon and a shape — never colour alone:
 *   Pass    circle + check, solid outline
 *   Fail    octagon + cross, solid outline
 *   Unknown diamond + question mark, dashed outline
 */
export function StatusBadge({ status, className, prefix }: { status: VerdictStatus; className?: string; prefix?: string }) {
  const { tone, Icon, dashed } = VERDICT[status];
  return (
    <span data-status={status} className="inline-flex">
      <Badge tone={tone} dashed={dashed} icon={<Icon size={16} />} className={className}>
        {prefix ? `${prefix} ${statusText(status)}` : statusText(status)}
      </Badge>
    </span>
  );
}

const LIFECYCLE: Record<RuleLifecycleStatus, { tone: BadgeTone; icon: ReactNode; dashed: boolean }> = {
  PROPOSED: { tone: "neutral", icon: <HollowCircleIcon size={16} />, dashed: true },
  CONFIRMED: { tone: "accent", icon: <CheckIcon size={16} />, dashed: false },
  SUPERSEDED: { tone: "neutral", icon: <SupersededIcon size={16} />, dashed: false },
};

/** Proposed — inactive / Confirmed — active / Superseded. */
export function RuleStatusBadge({ status }: { status: RuleLifecycleStatus }) {
  const { tone, icon, dashed } = LIFECYCLE[status];
  return (
    <span data-rule-status={status} className="inline-flex">
      <Badge tone={tone} icon={icon} dashed={dashed}>
        {ruleStatusLabel(status)}
      </Badge>
    </span>
  );
}

const JOB: Record<InvestigationStatus, { tone: BadgeTone; icon: ReactNode; dashed: boolean }> = {
  QUEUED: { tone: "neutral", icon: <ClockIcon size={16} />, dashed: true },
  RUNNING: { tone: "accent", icon: <ClockIcon size={16} />, dashed: true },
  SUCCEEDED: { tone: "accent", icon: <CheckIcon size={16} />, dashed: false },
  FAILED: { tone: "fail", icon: <ErrorIcon size={16} />, dashed: false },
};

/** Execution status of a job. Deliberately not a verdict: "Completed" says nothing about the rules. */
export function JobStatusBadge({ status }: { status: InvestigationStatus }) {
  const { tone, icon, dashed } = JOB[status];
  return (
    <span data-job-status={status} className="inline-flex">
      <Badge tone={tone} icon={icon} dashed={dashed}>
        {jobStatusText(status)}
      </Badge>
    </span>
  );
}

const COVERAGE: Record<CoverageStatus | "NOT_APPLICABLE", { tone: BadgeTone; icon: ReactNode; dashed: boolean }> = {
  COVERED: { tone: "neutral", icon: <CheckIcon size={16} />, dashed: false },
  PARTIAL: { tone: "unknown", icon: <WarningIcon size={16} />, dashed: true },
  MISSING: { tone: "unknown", icon: <UnknownIcon size={16} />, dashed: true },
  NOT_APPLICABLE: { tone: "neutral", icon: <InfoIcon size={16} />, dashed: false },
};

export function CoverageBadge({ status }: { status: CoverageStatus | "NOT_APPLICABLE" }) {
  const { tone, icon, dashed } = COVERAGE[status];
  return (
    <span data-coverage={status} className="inline-flex">
      <Badge tone={tone} icon={icon} dashed={dashed}>
        {coverageText(status)}
      </Badge>
    </span>
  );
}
