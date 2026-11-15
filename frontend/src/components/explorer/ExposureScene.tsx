"use client";

import { useEffect, useImperativeHandle, useRef, type Ref } from 'react';
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph';
import { CanvasTexture, Sprite, SpriteMaterial } from 'three';
import type { ExplorerReady } from './model';
import { exposureGraph, type ExposureNode, type ExposureLink } from './graph';

export interface SceneLabels {
  ticks: { position: number; text: string }[];
  limit: string | null;
  current: string;
  proposed: string;
}
export interface ExposureSceneHandle {
  rotate(direction: -1 | 1): void;
  zoom(direction: -1 | 1): void;
  reset(): void;
}
export interface ExposureSceneProps {
  model: ExplorerReady;
  labels: SceneLabels;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onFailure: (reason: 'INIT_FAILED' | 'CONTEXT_LOST') => void;
  ref?: Ref<ExposureSceneHandle>;
}

/** Lazy-loaded graph. Equal node sizes and link widths carry no financial quantity. */
export default function ExposureScene({ model, selectedId, onSelect, onFailure, ref }: ExposureSceneProps) {
  const host = useRef<HTMLDivElement>(null);
  const graph = useRef<ForceGraph3DInstance | null>(null);
  const callbacks = useRef({ onSelect, onFailure });
  useEffect(() => { callbacks.current = { onSelect, onFailure }; }, [onSelect, onFailure]);
  useImperativeHandle(ref, () => ({
    rotate(direction) {
      const g = graph.current;
      if (!g) return;
      const p = g.cameraPosition();
      const angle = direction * 0.2;
      g.cameraPosition({ x: p.x * Math.cos(angle) + p.z * Math.sin(angle), y: p.y, z: p.z * Math.cos(angle) - p.x * Math.sin(angle) }, { x: 0, y: 0, z: 0 }, 250);
    },
    zoom(direction) {
      const g = graph.current;
      if (!g) return;
      const p = g.cameraPosition();
      const factor = direction > 0 ? 0.85 : 1.15;
      g.cameraPosition({ x: p.x * factor, y: p.y * factor, z: p.z * factor }, { x: 0, y: 0, z: 0 }, 250);
    },
    reset() { graph.current?.zoomToFit(300, 30); },
  }), []);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let g: ForceGraph3DInstance | null = null;
    let resize: ResizeObserver | null = null;
    const textures: CanvasTexture[] = [];
    const materials: SpriteMaterial[] = [];
    const lost = (event: Event) => { event.preventDefault(); callbacks.current.onFailure('CONTEXT_LOST'); };
    const visibility = () => { if (document.hidden) g?.pauseAnimation(); else g?.resumeAnimation(); };
    try {
      const data = exposureGraph(model);
      g = new ForceGraph3D(element, { controlType: 'orbit', rendererConfig: { antialias: true, alpha: true } });
      graph.current = g;
      g.width(element.clientWidth).height(390).backgroundColor('#f3f7fc')
        .showNavInfo(false).enableNodeDrag(false).nodeRelSize(5).nodeVal(1).nodeOpacity(1)
        .nodeColor('color').linkColor(link => (link as ExposureLink).uncertain ? '#a16207' : '#94a3b8')
        .linkWidth(1.2).linkOpacity(0.7).linkDirectionalArrowLength(3)
        .nodeLabel(node => { const label = document.createElement('span'); label.textContent = String((node as ExposureNode).label); return label; })
        .nodeThreeObjectExtend(true)
        .nodeThreeObject(node => {
          const n = node as ExposureNode;
          const canvas = document.createElement('canvas');
          canvas.width = 512; canvas.height = 128;
          const ctx = canvas.getContext('2d');
          if (!ctx) return new Sprite();
          ctx.font = '600 48px system-ui'; ctx.textAlign = 'center'; ctx.fillStyle = '#16202b';
          n.label.split('\n').forEach((line, i) => ctx.fillText(line, 256, 50 + i * 52, 490));
          const texture = new CanvasTexture(canvas); textures.push(texture);
          const material = new SpriteMaterial({ map: texture, depthTest: false }); materials.push(material);
          const sprite = new Sprite(material); sprite.scale.set(200, 50, 1); sprite.position.y = -28;
          return sprite;
        })
        .onNodeClick(node => callbacks.current.onSelect((node as ExposureNode).segmentId ?? null))
        .onBackgroundClick(() => callbacks.current.onSelect(null))
        .cooldownTicks(80)
        .onEngineStop(() => { g?.cameraPosition({ x: 0, y: 0, z: 700 }, { x: 0, y: 0, z: 0 }); g?.zoomToFit(0, 45); })
        .graphData({ nodes: data.nodes.map(n => ({ ...n, fx: n.x, fy: n.y, fz: n.z })), links: data.links });
      g.cameraPosition({ x: 0, y: 0, z: 650 });
      const canvas = g.renderer().domElement;
      canvas.setAttribute('aria-hidden', 'true'); canvas.tabIndex = -1;
      canvas.addEventListener('webglcontextlost', lost);
      resize = new ResizeObserver(() => g?.width(Math.max(1, element.clientWidth)));
      resize.observe(element);
      document.addEventListener('visibilitychange', visibility);
      visibility();
    } catch {
      callbacks.current.onFailure('INIT_FAILED');
    }
    return () => {
      resize?.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      g?.renderer().domElement.removeEventListener('webglcontextlost', lost);
      g?._destructor();
      textures.forEach(t => t.dispose()); materials.forEach(m => m.dispose());
      graph.current = null;
      element.replaceChildren();
    };
  }, [model]);

  useEffect(() => {
    graph.current?.nodeColor(node => (node as ExposureNode).segmentId === selectedId && selectedId ? '#7c3aed' : String((node as ExposureNode).color));
  }, [selectedId, model]);

  return <div ref={host} className="h-[390px] min-w-0 w-full overflow-hidden rounded-xl border border-line" data-testid="explorer-scene" aria-hidden="true" />;
}
