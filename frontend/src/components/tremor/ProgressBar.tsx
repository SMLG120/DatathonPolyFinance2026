// Adapted from Tremor ProgressBar v0.0.3 (Apache-2.0; see licenses/tremor.txt).
// Uses the app palette, finite bounds and reduced-motion-aware animation.
import { forwardRef, type ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";
import { t } from "@/lib/i18n";

interface ProgressBarProps extends ComponentPropsWithoutRef<"div"> {
  value: number;
  max?: number;
  label?: string;
}
export const ProgressBar = forwardRef<HTMLDivElement, ProgressBarProps>(
  ({ value, max = 100, label, className, ...props }, ref) => {
    const ceiling = Number.isFinite(max) && max > 0 ? max : 100;
    const safeValue = Number.isFinite(value) ? Math.min(ceiling, Math.max(value, 0)) : 0;
    return (
      <div ref={ref} className={cn("flex w-full items-center", className)} role="progressbar" aria-label={t("Progress")} aria-valuemin={0} aria-valuenow={safeValue} aria-valuemax={ceiling} data-tremor="progress-bar" {...props}>
        <div className="relative flex h-1.5 w-full items-center rounded-full bg-accent-soft">
          <div className="h-full rounded-full bg-accent motion-safe:transition-[width] motion-safe:duration-300" style={{ width: `${safeValue / ceiling * 100}%` }} />
        </div>
        {label ? <span className="ml-2 whitespace-nowrap text-sm font-medium text-ink">{label}</span> : null}
      </div>
    );
  },
);
ProgressBar.displayName = "ProgressBar";
