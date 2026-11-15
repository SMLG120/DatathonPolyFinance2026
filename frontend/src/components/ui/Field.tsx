import type { InputHTMLAttributes, ReactNode, Ref, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import { ErrorIcon } from "./icons";

const CONTROL =
  "w-full rounded-md border bg-surface px-3 text-base text-ink placeholder:text-ink-muted " +
  "border-line-strong aria-invalid:border-fail aria-invalid:border-2";

export interface FieldProps {
  /** id of the control this field labels. */
  htmlFor: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function hintId(controlId: string): string {
  return `${controlId}-hint`;
}

export function errorId(controlId: string): string {
  return `${controlId}-error`;
}

/** The ids a control must list in `aria-describedby` for its hint and error to be announced. */
export function describedBy(controlId: string, options: { hint?: boolean; error?: boolean }): string | undefined {
  const ids = [options.hint ? hintId(controlId) : null, options.error ? errorId(controlId) : null].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

/** A label, an optional hint and an optional error message around one control. */
export function Field({ htmlFor, label, hint, error, children, className }: FieldProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block font-semibold text-ink">
        {label}
      </label>
      {hint ? (
        <p id={hintId(htmlFor)} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p id={errorId(htmlFor)} className="flex items-start gap-1.5 text-sm font-semibold text-fail">
          <ErrorIcon size={16} className="mt-0.5 flex-none" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  );
}

export function TextInput({ className, ref, ...props }: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  return <input ref={ref} className={cn(CONTROL, "min-h-11", className)} {...props} />;
}

export function TextArea({ className, ref, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }) {
  return <textarea ref={ref} className={cn(CONTROL, "py-2 leading-6", className)} {...props} />;
}

export function Select({ className, ref, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { ref?: Ref<HTMLSelectElement> }) {
  return (
    <select ref={ref} className={cn(CONTROL, "min-h-11 pr-8", className)} {...props}>
      {children}
    </select>
  );
}
