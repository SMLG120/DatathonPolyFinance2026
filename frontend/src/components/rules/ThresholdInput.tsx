"use client";

import type { Ref } from "react";
import { describedBy, errorId, hintId } from "@/components/ui/Field";
import { ErrorIcon } from "@/components/ui/icons";
import { cn } from "@/lib/cn";
import { percentInputToFraction } from "@/lib/format";

export interface ThresholdInputProps {
  id: string;
  label: string;
  hint?: string;
  /** The percentage exactly as typed. An empty string means "not set" — never zero. */
  value: string;
  onChange: (text: string) => void;
  error?: string | null;
  /** Upper end of the slider, in percent. The number field accepts anything from 0 to 100. */
  sliderMax?: number;
  inputRef?: Ref<HTMLInputElement>;
}

const SLIDER_STEP = 0.5;

/**
 * A threshold as a number field plus a slider, both editing the same text.
 *
 * While nothing is entered the field is empty and the slider is drawn hollow
 * and announced as "Not set": a system-proposed rule never shows a number the
 * user did not choose.
 */
export function ThresholdInput({ id, label, hint, value, onChange, error, sliderMax = 50, inputRef }: ThresholdInputProps) {
  const fraction = percentInputToFraction(value);
  const percent = fraction === null ? null : fraction * 100;
  const isSet = percent !== null;
  // Keep the thumb on the track when a larger number is typed.
  const max = percent !== null && percent > sliderMax ? Math.min(100, Math.ceil(percent / 10) * 10) : sliderMax;

  return (
    <div className="space-y-1.5" data-testid="threshold-input">
      <label htmlFor={id} className="block font-semibold text-ink">
        {label}
      </label>
      {hint ? (
        <p id={hintId(id)} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-5">
        <div className="flex items-center gap-2">
          <input
            id={id}
            ref={inputRef}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="Not set"
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy(id, { hint: Boolean(hint), error: Boolean(error) })}
            className={cn(
              "tabular min-h-11 w-28 rounded-md border border-line-strong bg-surface px-3 text-right text-lg font-semibold text-ink",
              "placeholder:text-base placeholder:font-normal placeholder:text-ink-muted aria-invalid:border-2 aria-invalid:border-fail",
            )}
          />
          <span className="text-lg font-semibold text-ink" aria-hidden="true">
            %
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <input
            type="range"
            className="byb-range block w-full"
            min={0}
            max={max}
            step={SLIDER_STEP}
            value={percent === null ? 0 : Math.min(percent, max)}
            data-unset={isSet ? undefined : "true"}
            aria-label={`${label}, slider from 0 to ${max} percent`}
            aria-valuetext={isSet ? `${value.trim().replace(/%$/, "")} percent` : "Not set"}
            onChange={(event) => onChange(event.target.value)}
          />
          <div className="tabular mt-0.5 flex justify-between text-sm text-ink-muted" aria-hidden="true">
            <span>0%</span>
            <span>{max}%</span>
          </div>
        </div>
      </div>
      {error ? (
        <p id={errorId(id)} className="flex items-start gap-1.5 text-sm font-semibold text-fail">
          <ErrorIcon size={16} className="mt-0.5 flex-none" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}
