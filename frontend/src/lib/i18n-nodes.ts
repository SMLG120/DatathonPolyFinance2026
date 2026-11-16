import { createElement, Fragment, type ReactNode } from "react";
import { t } from "@/lib/i18n";

/**
 * Like tf(), but the inserted values may be React elements (a figure in its own <span>, a link), so a whole sentence
 * stays one catalog entry while its figures keep their markup. "Cash goes from {before} to {after}." in English renders
 * the same text as before; a translation may reorder the values.
 */
export function tn(template: string, values: Record<string, ReactNode>): ReactNode[] {
  return t(template)
    .split(/\{(\w+)\}/g)
    .map((part, index) => (index % 2 === 0 ? part : createElement(Fragment, { key: index }, part in values ? values[part] : `{${part}}`)));
}
