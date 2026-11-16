"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { describedBy, Field, TextInput } from "@/components/ui/Field";
import { LockIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/Notice";
import { describeError, isApiError } from "@/lib/api";
import { useRuntime } from "@/state/runtime";
import { t } from "@/lib/i18n";

/**
 * Asks for the demo access code at runtime.
 *
 * The code is typed here, checked against the service, and kept in
 * sessionStorage for this tab only. It is never part of the built files, never
 * placed in a URL and never written to the console.
 */
export function AccessCodeForm() {
  const { submitAccessCode, accessCodeRejected } = useRuntime();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (code.trim() === "") {
      setFieldError("Enter the access code you were given.");
      setRequestError(null);
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setFieldError(null);
    setRequestError(null);
    try {
      await submitAccessCode(code);
      // On success the form is replaced by the simulation.
    } catch (error) {
      if (isApiError(error) && error.kind === "unauthorized") {
        setFieldError("The service did not accept this code. Check it and try again.");
        inputRef.current?.focus();
      } else {
        setRequestError(describeError(error));
      }
      setBusy(false);
    }
  }

  return (
    <article aria-labelledby="access-title" className="mx-auto max-w-xl space-y-6">
      <header className="space-y-2">
        <h1 id="access-title" data-stage-heading tabIndex={-1} className="text-3xl font-bold tracking-tight text-ink">
          {t("Enter the access code")}</h1>
        <p className="text-lg text-ink-muted">{t("This demonstration talks to a private service. The access code was given to you with the demo link.")}</p>
      </header>

      {accessCodeRejected && !fieldError ? (
        <Notice tone="caution" role="status" title={t("The service no longer accepts the code that was in use")}>
          <p>{t("It has been removed from this tab. Enter the code again to continue. Nothing you did was lost.")}</p>
        </Notice>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-5 rounded-lg border border-line bg-surface p-4 sm:p-6">
        <Field
          htmlFor={inputId}
          label={t("Access code")}
          hint={t("Kept for this browser tab only and removed when the tab closes. It is never stored in the page's files.")}
          error={fieldError}
        >
          <TextInput
            id={inputId}
            ref={inputRef}
            name="access-code"
            type={show ? "text" : "password"}
            value={code}
            onChange={(event) => {
              setCode(event.target.value);
              if (fieldError) setFieldError(null);
            }}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={describedBy(inputId, { hint: true, error: Boolean(fieldError) })}
          />
        </Field>

        <label className="flex min-h-11 items-center gap-3 text-ink">
          <input type="checkbox" checked={show} onChange={(event) => setShow(event.target.checked)} className="size-5 accent-accent" />
          <span>{t("Show the code as I type")}</span>
        </label>

        {requestError ? (
          <Notice tone="error" role="alert" title={t("The code could not be checked")}>
            <p>{requestError}</p>
            <p>{t("Nothing was stored. You can try again.")}</p>
          </Notice>
        ) : null}

        <Button type="submit" variant="primary" busy={busy} busyLabel="Checking the code…" icon={<LockIcon />}>
          {t("Continue")}</Button>
      </form>

      <p className="text-ink-muted">
        {t("No code?")}{" "}
        <a href="?fixtures=1" className="font-semibold text-accent underline underline-offset-4 hover:text-accent-strong">
          {t("Open the simulation with test data")}</a>{" "}
        {t("instead. Test data needs no service and is labelled on every screen.")}</p>
    </article>
  );
}
