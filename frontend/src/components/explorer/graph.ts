import type { ExplorerReady } from './model';
import { formatFraction } from '@/lib/format';
import { t, tf } from '@/lib/i18n';

export interface ExposureNode {
  id: string;
  label: string;
  color: string;
  segmentId: string | null;
  uncertain: boolean;
  x: number; y: number; z: number;
}
export interface ExposureLink { source: string; target: string; uncertain: boolean }

/** Relationships only; all financial figures are copied from the checked model. */
export function exposureGraph(model: ExplorerReady) {
  const nodes: ExposureNode[] = [];
  const links: ExposureLink[] = [];
  for (const [index, column] of [model.current, model.proposed].entries()) {
    const x = index === 0 ? -190 : 190;
    const root = `${column.state}:portfolio`;
    const issuer = `${column.state}:issuer`;
    nodes.push({ id: root, label: index === 0 ? t("Current portfolio") : t("Proposed portfolio"), color: '#334155', segmentId: null, uncertain: false, x, y: 100, z: 0 });
    nodes.push({ id: issuer, label: model.issuerName, color: '#0f766e', segmentId: null, uncertain: false, x, y: -100, z: 0 });
    column.segments.forEach((segment, i) => {
      const uncertain = segment.kind === 'UNRESOLVED';
      const name = uncertain ? t("Not attributed") : segment.kind === 'DIRECT' ? t("Held directly") : tf("Via {fund}", { fund: String(segment.fundId) });
      const value = uncertain ? tf("Up to {value}", { value: formatFraction(segment.value) }) : formatFraction(segment.value);
      nodes.push({ id: segment.id, label: `${name}\n${value}`, color: uncertain ? '#a16207' : segment.kind === 'DIRECT' ? '#1d4e89' : '#5c88bf', segmentId: segment.id, uncertain, x: x + (i - (column.segments.length - 1) / 2) * 110, y: 0, z: 0 });
      links.push({ source: root, target: segment.id, uncertain });
      // Missing holdings do not prove a connection to this issuer.
      if (!uncertain) links.push({ source: segment.id, target: issuer, uncertain: false });
    });
  }
  return { nodes, links };
}
