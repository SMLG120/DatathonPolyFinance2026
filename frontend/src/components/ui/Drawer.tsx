"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { CloseIcon } from "./icons";

export interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  /** Accessible name of the close button, e.g. "Close evidence". */
  closeLabel: string;
  /**
   * The control that opened the drawer. Focus goes back to it on close. Radix
   * restores focus to whatever was focused before, but Safari does not focus a
   * button when it is clicked, so the opener is passed explicitly.
   */
  returnFocusTo?: () => HTMLElement | null;
}

/**
 * A side sheet built on Radix Dialog, which provides the parts that are easy
 * to get wrong by hand: focus is moved in and trapped, the page behind is
 * inert and hidden from assistive technology, Escape and the overlay close it,
 * and focus returns to the control that opened it.
 */
export function Drawer({ open, onOpenChange, title, description, children, closeLabel, returnFocusTo }: DrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="byb-overlay fixed inset-0 z-40 bg-ink/50" />
        <Dialog.Content
          className="byb-drawer fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-line bg-surface shadow-2xl focus:outline-none"
          {...(description ? {} : { "aria-describedby": undefined })}
          onCloseAutoFocus={(event) => {
            const target = returnFocusTo?.();
            if (target && target.isConnected) {
              event.preventDefault();
              target.focus();
            }
          }}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-4 sm:px-6">
            <div className="min-w-0 space-y-1">
              <Dialog.Title className="text-xl font-semibold text-ink">{title}</Dialog.Title>
              {description ? <Dialog.Description className="text-ink-muted">{description}</Dialog.Description> : null}
            </div>
            <Dialog.Close
              aria-label={closeLabel}
              className="inline-flex size-11 flex-none items-center justify-center rounded-md border border-line-strong bg-surface text-ink hover:bg-sunken"
            >
              <CloseIcon />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
