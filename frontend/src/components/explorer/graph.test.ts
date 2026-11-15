import { describe, it, expect } from 'vitest';
import { exposureGraph } from './graph';
import { buildExplorerModel } from './model';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { CheckResult } from './contract-types';

describe('ownership graph evidence boundaries', () => {
  it('keeps unknown amounts separate from proven issuer paths and preserves inputs', () => {
    const payload = JSON.parse(readFileSync(path.resolve(import.meta.dirname, '../../../../contracts/fixtures/api/investigation_robert_succeeded.json'), 'utf8'));
    const model = buildExplorerModel(payload.response_body.result as CheckResult, { dataOrigin: 'FIXTURE' });
    if (model.status !== 'READY') throw Error('Expected ready fixture');
    model.current.segments = model.current.segments.filter(s => s.kind !== 'UNRESOLVED');
    model.current.segments.push({ id: 'starting:UNRESOLVED', kind: 'UNRESOLVED', state: 'starting', value: 0.12, fundId: null, holdingsDate: null, sourceId: null, coverageStatus: null, evidenceId: null, formula: null });
    const before = structuredClone(model);
    const graph = exposureGraph(model);
    expect(graph.links.some(l => l.source === 'starting:UNRESOLVED' && l.target === 'starting:issuer')).toBe(false);
    expect(graph.nodes.find(n => n.id === 'starting:UNRESOLVED')?.label).toContain('Up to');
    expect(new Set(graph.nodes.map(n => n.id)).size).toBe(graph.nodes.length);
    for (const link of graph.links) {
      expect(graph.nodes.some(n => n.id === link.source)).toBe(true);
      expect(graph.nodes.some(n => n.id === link.target)).toBe(true);
    }
    expect(model).toEqual(before);
  });
});
