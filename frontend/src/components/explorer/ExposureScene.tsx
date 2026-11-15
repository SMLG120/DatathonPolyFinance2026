"use client";

/**
 * The 3D drawing of the exposure explorer. The ONLY file that imports `three`;
 * it is loaded lazily by `ExposureExplorer`, so no other page pays for it.
 *
 * What is drawn, and nothing more:
 * - two stacked columns (current, proposed) on ONE scale: height = value / axisMax;
 * - every segment has the same width and depth, which mean nothing;
 * - the limit as a thin horizontal plane across both columns;
 * - light scale lines.
 *
 * The drawing is decoration for assistive technology: the canvas is hidden from
 * it and has no tab stop. Every value is in the HTML table next to it, and every
 * segment can be selected with the HTML buttons. Label text arrives ready-made
 * from the caller; this file formats and computes no financial value.
 */
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import {
  AmbientLight,
  BoxGeometry,
  BufferGeometry,
  Color,
  DirectionalLight,
  DoubleSide,
  EdgesGeometry,
  Float32BufferAttribute,
  LineBasicMaterial,
  LineDashedMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshLambertMaterial,
  OrthographicCamera,
  PlaneGeometry,
  Raycaster,
  Scene,
  Vector2,
  Vector3,
  WebGLRenderer,
  type Material,
} from "three";
import { REDUCED_MOTION_QUERY } from "./capability";
import type { ExplorerReady, ExplorerSegment, SegmentKind } from "./model";

/** Text placed over the canvas as HTML. Written by the caller from the model; never computed here. */
export interface SceneLabels {
  /** Scale lines: `position` is the share of the scale height (0 to 1); `text` is its label. */
  ticks: { position: number; text: string }[];
  /** Null when the model has no limit. */
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
  onSelect: (segmentId: string | null) => void;
  /** The scene cannot continue; the caller switches to its fallback. */
  onFailure: (reason: "INIT_FAILED" | "CONTEXT_LOST") => void;
  ref?: Ref<ExposureSceneHandle>;
}

// World units. Presentation only.
const SCALE_HEIGHT = 4;
const COLUMN_WIDTH = 1.2;
const COLUMN_DEPTH = 1.2;
const COLUMN_X = { starting: -1.25, proposed: 1.25 } as const;
const HALF_SPAN = 2.6;

// The view: rotation and zoom are deliberately narrow, so the two columns never swap sides or leave the frame.
const HOME = { yaw: -0.4, pitch: 0.3, zoom: 1 } as const;
const YAW_LIMIT = 0.61; // about 35 degrees either way
const PITCH_MIN = 0.12;
const PITCH_MAX = 0.6;
const ZOOM_MIN = 0.75;
const ZOOM_MAX = 1.8;
const ROTATE_STEP = 0.15;
const ZOOM_STEP = 1.15;
const TWEEN_MS = 300;
const CLICK_SLOP_PX = 5;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const TOKEN_FALLBACK: Record<string, string> = {
  "--color-chart-direct": "#1d4e89",
  "--color-chart-indirect": "#5c88bf",
  "--color-chart-track": "#e7eef7",
  "--color-surface": "#ffffff",
  "--color-ink": "#16202b",
  "--color-line": "#d3d8df",
};

/** A design token as a colour, read from the page so the scene matches the 2D chart. */
function token(name: string): Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const color = new Color();
  try {
    color.set(value || (TOKEN_FALLBACK[name] ?? "#000000"));
  } catch {
    color.set(TOKEN_FALLBACK[name] ?? "#000000");
  }
  return color;
}

interface KindMaterials {
  base: Material;
  hover: Material;
  dim: Material;
}

interface SegmentObject {
  id: string;
  state: ExplorerSegment["state"];
  kind: SegmentKind;
  mesh: Mesh;
  edges: LineSegments | null;
  /** Height in world units being drawn now, and where the tween started and ends. */
  height: number;
  from: number;
  to: number;
}

interface Label {
  element: HTMLElement;
  anchor: Vector3;
}

/**
 * Everything WebGL, outside React. One instance per mounted scene. It renders
 * only when asked (`invalidate`), one animation frame per request.
 */
class SceneEngine {
  private readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
  private readonly raycaster = new Raycaster();
  private readonly pointer = new Vector2();
  private readonly projected = new Vector3();

  // One geometry for every segment, scaled per mesh; its origin is at the base so scaling grows upward.
  private readonly box = new BoxGeometry(1, 1, 1).translate(0, 0.5, 0);
  private readonly boxEdges = new EdgesGeometry(this.box);
  private readonly limitPlane = new PlaneGeometry(HALF_SPAN * 2, COLUMN_DEPTH * 1.5).rotateX(-Math.PI / 2);
  private readonly limitEdges = new EdgesGeometry(this.limitPlane);
  private readonly floorPlane = new PlaneGeometry(HALF_SPAN * 2, COLUMN_DEPTH * 1.5).rotateX(-Math.PI / 2);
  private tickGeometry: BufferGeometry | null = null;

  private readonly materials: Record<SegmentKind, KindMaterials>;
  private readonly fundEdgeMaterial: LineBasicMaterial;
  private readonly unresolvedEdgeMaterial: LineDashedMaterial;
  private readonly limitMaterial: MeshBasicMaterial;
  private readonly limitEdgeMaterial: LineBasicMaterial;
  private readonly draftLimitEdgeMaterial: LineDashedMaterial;
  private readonly floorMaterial: MeshBasicMaterial;
  private readonly tickMaterial: LineBasicMaterial;

  private readonly floor: Mesh;
  private readonly limitMesh: Mesh;
  private readonly limitOutline: LineSegments;
  private ticks: LineSegments | null = null;

  private segments: SegmentObject[] = [];
  private labels: Label[] = [];
  private limitLabel: Label | null = null;
  private limitHeight = { now: 0, from: 0, to: 0 };
  private hasModel = false;
  private tweenStart: number | null = null;

  private selectedId: string | null = null;
  private hoveredId: string | null = null;

  private view: { yaw: number; pitch: number; zoom: number } = { ...HOME };
  private frame = 0;
  private disposed = false;

  private readonly pointers = new Map<number, { x: number; y: number }>();
  private dragDistance = 0;
  private pinchDistance = 0;

  private readonly resizeObserver: ResizeObserver;

  constructor(
    private readonly host: HTMLElement,
    private readonly overlay: HTMLElement,
    private readonly callbacks: { onSelect: (id: string | null) => void; onContextLost: () => void },
  ) {
    this.renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    const canvas = this.renderer.domElement;
    canvas.setAttribute("aria-hidden", "true");
    canvas.tabIndex = -1;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    // Vertical page scrolling stays with the browser; a sideways drag turns the view.
    canvas.style.touchAction = "pan-y";
    host.appendChild(canvas);

    const direct = token("--color-chart-direct");
    const indirect = token("--color-chart-indirect");
    const surface = token("--color-surface");
    const ink = token("--color-ink");

    const solid = (color: Color): KindMaterials => ({
      base: new MeshLambertMaterial({ color }),
      hover: new MeshLambertMaterial({ color: color.clone().lerp(surface, 0.25) }),
      // Unselected solid parts stay clearly solid: a faint body would read as "not attributed".
      dim: new MeshLambertMaterial({ color, transparent: true, opacity: 0.8 }),
    });
    // "Not attributed" is hollow: a faint see-through body with a dashed outline, never a solid block.
    const hollow = (): KindMaterials => ({
      base: new MeshBasicMaterial({ color: surface, transparent: true, opacity: 0.15, depthWrite: false }),
      hover: new MeshBasicMaterial({ color: indirect, transparent: true, opacity: 0.3, depthWrite: false }),
      dim: new MeshBasicMaterial({ color: surface, transparent: true, opacity: 0.05, depthWrite: false }),
    });
    this.materials = { DIRECT: solid(direct), FUND: solid(indirect), UNRESOLVED: hollow() };
    this.fundEdgeMaterial = new LineBasicMaterial({ color: ink });
    this.unresolvedEdgeMaterial = new LineDashedMaterial({ color: direct, dashSize: 0.09, gapSize: 0.07 });
    this.limitMaterial = new MeshBasicMaterial({ color: ink, transparent: true, opacity: 0.22, side: DoubleSide, depthWrite: false });
    this.limitEdgeMaterial = new LineBasicMaterial({ color: ink });
    this.draftLimitEdgeMaterial = new LineDashedMaterial({ color: ink, dashSize: 0.14, gapSize: 0.1 });
    this.floorMaterial = new MeshBasicMaterial({ color: token("--color-chart-track"), side: DoubleSide });
    this.tickMaterial = new LineBasicMaterial({ color: token("--color-line") });

    this.scene.add(new AmbientLight(0xffffff, 2.2));
    const sun = new DirectionalLight(0xffffff, 1.6);
    sun.position.set(3, 6, 5);
    this.scene.add(sun);

    this.floor = new Mesh(this.floorPlane, this.floorMaterial);
    this.floor.position.y = -0.005;
    this.scene.add(this.floor);

    this.limitMesh = new Mesh(this.limitPlane, this.limitMaterial);
    this.limitOutline = new LineSegments(this.limitEdges, this.limitEdgeMaterial);
    this.limitOutline.computeLineDistances();
    this.limitMesh.visible = false;
    this.limitOutline.visible = false;
    this.limitMesh.renderOrder = 2;
    this.limitOutline.renderOrder = 3;
    this.scene.add(this.limitMesh, this.limitOutline);

    canvas.addEventListener("pointerdown", this.onPointerDown);
    canvas.addEventListener("pointermove", this.onPointerMove);
    canvas.addEventListener("pointerup", this.onPointerUp);
    canvas.addEventListener("pointercancel", this.onPointerCancel);
    canvas.addEventListener("pointerleave", this.onPointerLeave);
    canvas.addEventListener("wheel", this.onWheel, { passive: false });
    canvas.addEventListener("webglcontextlost", this.onContextLost);
    document.addEventListener("visibilitychange", this.onVisibilityChange);
    window.addEventListener("resize", this.onResize);
    this.resizeObserver = new ResizeObserver(this.onResize);
    this.resizeObserver.observe(host);

    this.resize();
  }

  // ---- model ---------------------------------------------------------------

  setModel(model: ExplorerReady, labels: SceneLabels): void {
    if (this.disposed) return;
    const animate = this.hasModel && !window.matchMedia(REDUCED_MOTION_QUERY).matches;
    const previous = new Map(this.segments.map((segment) => [segment.id, segment.height]));

    for (const segment of this.segments) {
      this.scene.remove(segment.mesh);
      if (segment.edges) this.scene.remove(segment.edges);
    }
    this.segments = [];

    const worldHeight = (value: number) => (model.axisMax > 0 ? (value / model.axisMax) * SCALE_HEIGHT : 0);

    for (const column of [model.current, model.proposed]) {
      for (const part of column.segments) {
        if (!(part.value > 0)) continue; // nothing to draw; the HTML table still shows the value
        const to = worldHeight(part.value);
        const from = animate ? (previous.get(part.id) ?? 0) : to;
        const mesh = new Mesh(this.box, this.materials[part.kind].base);
        mesh.userData.segmentId = part.id;
        let edges: LineSegments | null = null;
        if (part.kind === "FUND") edges = new LineSegments(this.boxEdges, this.fundEdgeMaterial);
        if (part.kind === "UNRESOLVED") {
          edges = new LineSegments(this.boxEdges, this.unresolvedEdgeMaterial);
          edges.computeLineDistances();
        }
        this.scene.add(mesh);
        if (edges) this.scene.add(edges);
        this.segments.push({ id: part.id, state: part.state, kind: part.kind, mesh, edges, height: from, from, to });
      }
    }

    // Limit plane.
    const limitTo = model.limit ? worldHeight(model.limit.value) : 0;
    this.limitMesh.visible = model.limit !== null;
    this.limitOutline.visible = model.limit !== null;
    this.limitOutline.material = model.limit?.isDraft ? this.draftLimitEdgeMaterial : this.limitEdgeMaterial;
    const limitFrom = animate ? this.limitHeight.now : limitTo;
    this.limitHeight = { now: limitFrom, from: limitFrom, to: limitTo };

    // Scale lines at the columns' own depth (z = 0), the same depth as the scale and limit labels,
    // so a label and the line or plane it names are never offset from each other by the view angle.
    if (this.ticks) this.scene.remove(this.ticks);
    this.tickGeometry?.dispose();
    const points: number[] = [];
    for (const tick of labels.ticks) {
      const y = tick.position * SCALE_HEIGHT;
      points.push(-HALF_SPAN, y, 0, HALF_SPAN, y, 0);
    }
    this.tickGeometry = new BufferGeometry();
    this.tickGeometry.setAttribute("position", new Float32BufferAttribute(points, 3));
    this.ticks = new LineSegments(this.tickGeometry, this.tickMaterial);
    this.scene.add(this.ticks);

    this.buildLabels(labels);
    this.hasModel = true;
    this.tweenStart = animate ? performance.now() : null;
    this.layoutSegments();
    this.applyHighlight();
    this.invalidate();
  }

  private buildLabels(labels: SceneLabels): void {
    this.overlay.replaceChildren();
    this.labels = [];
    this.limitLabel = null;
    const add = (text: string, className: string, anchor: Vector3): Label => {
      const element = document.createElement("span");
      element.textContent = text;
      element.className = `pointer-events-none absolute whitespace-nowrap ${className}`;
      this.overlay.appendChild(element);
      const label = { element, anchor };
      this.labels.push(label);
      return label;
    };
    for (const tick of labels.ticks) {
      add(tick.text, "tabular -translate-x-full -translate-y-1/2 pr-1.5 text-xs text-ink-muted", new Vector3(-HALF_SPAN, tick.position * SCALE_HEIGHT, 0));
    }
    const front = COLUMN_DEPTH * 0.75;
    add(labels.current, "-translate-x-1/2 pt-1.5 text-sm font-semibold text-ink", new Vector3(COLUMN_X.starting, 0, front));
    add(labels.proposed, "-translate-x-1/2 pt-1.5 text-sm font-semibold text-ink", new Vector3(COLUMN_X.proposed, 0, front));
    if (labels.limit !== null) {
      this.limitLabel = add(
        labels.limit,
        "tabular -translate-y-full rounded-sm bg-surface px-1 text-xs font-semibold text-ink",
        new Vector3(-HALF_SPAN, this.limitHeight.now, 0),
      );
    }
  }

  /** Stacks each column from the base up, using the heights being drawn now. */
  private layoutSegments(): void {
    const base = { starting: 0, proposed: 0 };
    for (const segment of this.segments) {
      const y = base[segment.state];
      for (const object of [segment.mesh, segment.edges]) {
        if (!object) continue;
        object.position.set(COLUMN_X[segment.state], y, 0);
        object.scale.set(COLUMN_WIDTH, Math.max(segment.height, 1e-4), COLUMN_DEPTH);
      }
      base[segment.state] = y + segment.height;
    }
    this.limitMesh.position.y = this.limitHeight.now;
    this.limitOutline.position.y = this.limitHeight.now;
    if (this.limitLabel) this.limitLabel.anchor.y = this.limitHeight.now;
  }

  // ---- selection -----------------------------------------------------------

  setSelection(id: string | null): void {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this.applyHighlight();
    this.invalidate();
  }

  private applyHighlight(): void {
    const selectedExists = this.selectedId !== null && this.segments.some((segment) => segment.id === this.selectedId);
    for (const segment of this.segments) {
      const set = this.materials[segment.kind];
      const material = segment.id === this.hoveredId ? set.hover : selectedExists && segment.id !== this.selectedId ? set.dim : set.base;
      segment.mesh.material = material;
    }
  }

  // ---- view ----------------------------------------------------------------

  rotateBy(yaw: number, pitch = 0): void {
    this.view.yaw = clamp(this.view.yaw + yaw, -YAW_LIMIT, YAW_LIMIT);
    this.view.pitch = clamp(this.view.pitch + pitch, PITCH_MIN, PITCH_MAX);
    this.invalidate();
  }

  zoomBy(factor: number): void {
    this.view.zoom = clamp(this.view.zoom * factor, ZOOM_MIN, ZOOM_MAX);
    this.invalidate();
  }

  resetView(): void {
    this.view = { ...HOME };
    this.invalidate();
  }

  private resize(): void {
    const width = Math.max(1, this.host.clientWidth);
    const height = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(width, height, false);
    const aspect = width / height;
    const halfHeight = Math.max(SCALE_HEIGHT / 2 + 1.1, (HALF_SPAN + 1.5) / aspect);
    this.camera.left = -halfHeight * aspect;
    this.camera.right = halfHeight * aspect;
    this.camera.top = halfHeight;
    this.camera.bottom = -halfHeight;
  }

  // ---- rendering -----------------------------------------------------------

  /** Asks for one frame. Does nothing while a frame is pending or the tab is hidden. */
  invalidate(): void {
    if (this.disposed || this.frame !== 0 || document.hidden) return;
    this.frame = requestAnimationFrame(this.draw);
  }

  private readonly draw = (now: number): void => {
    this.frame = 0;
    if (this.disposed) return;

    if (this.tweenStart !== null) {
      const progress = clamp((now - this.tweenStart) / TWEEN_MS, 0, 1);
      const eased = 1 - (1 - progress) ** 3;
      for (const segment of this.segments) segment.height = segment.from + (segment.to - segment.from) * eased;
      this.limitHeight.now = this.limitHeight.from + (this.limitHeight.to - this.limitHeight.from) * eased;
      this.layoutSegments();
      if (progress >= 1) this.tweenStart = null;
      else this.invalidate();
    }

    const { yaw, pitch, zoom } = this.view;
    const centre = SCALE_HEIGHT / 2;
    const distance = 20;
    this.camera.position.set(Math.sin(yaw) * Math.cos(pitch) * distance, centre + Math.sin(pitch) * distance, Math.cos(yaw) * Math.cos(pitch) * distance);
    this.camera.lookAt(0, centre, 0);
    this.camera.zoom = zoom;
    this.camera.updateProjectionMatrix();
    this.renderer.render(this.scene, this.camera);

    const width = this.host.clientWidth;
    const height = this.host.clientHeight;
    for (const label of this.labels) {
      this.projected.copy(label.anchor).project(this.camera);
      label.element.style.left = `${((this.projected.x + 1) / 2) * width}px`;
      label.element.style.top = `${((1 - this.projected.y) / 2) * height}px`;
    }
  };

  // ---- input ---------------------------------------------------------------

  private pick(event: PointerEvent): string | null {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(
      this.segments.map((segment) => segment.mesh),
      false,
    )[0];
    return typeof hit?.object.userData.segmentId === "string" ? hit.object.userData.segmentId : null;
  }

  private setHover(id: string | null): void {
    if (this.hoveredId === id) return;
    this.hoveredId = id;
    this.renderer.domElement.style.cursor = id ? "pointer" : "grab";
    this.applyHighlight();
    this.invalidate();
  }

  private pinchSpan(): number {
    const [a, b] = [...this.pointers.values()];
    return a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 0;
  }

  private readonly onPointerDown = (event: PointerEvent): void => {
    this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    this.renderer.domElement.setPointerCapture?.(event.pointerId);
    if (this.pointers.size === 1) this.dragDistance = 0;
    if (this.pointers.size === 2) this.pinchDistance = this.pinchSpan();
  };

  private readonly onPointerMove = (event: PointerEvent): void => {
    const last = this.pointers.get(event.pointerId);
    if (!last) {
      this.setHover(this.pick(event));
      return;
    }
    const dx = event.clientX - last.x;
    const dy = event.clientY - last.y;
    this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (this.pointers.size === 1) {
      this.dragDistance += Math.abs(dx) + Math.abs(dy);
      if (this.dragDistance > CLICK_SLOP_PX) this.rotateBy(-dx * 0.008, dy * 0.006);
    } else if (this.pointers.size === 2) {
      const span = this.pinchSpan();
      if (this.pinchDistance > 0 && span > 0) this.zoomBy(span / this.pinchDistance);
      this.pinchDistance = span;
      this.dragDistance = CLICK_SLOP_PX + 1; // a pinch is never a click
    }
  };

  private readonly onPointerUp = (event: PointerEvent): void => {
    const wasSingle = this.pointers.size === 1 && this.pointers.has(event.pointerId);
    this.pointers.delete(event.pointerId);
    if (wasSingle && this.dragDistance <= CLICK_SLOP_PX) this.callbacks.onSelect(this.pick(event));
  };

  private readonly onPointerCancel = (event: PointerEvent): void => {
    this.pointers.delete(event.pointerId);
  };

  private readonly onPointerLeave = (): void => {
    if (this.pointers.size === 0) this.setHover(null);
  };

  private readonly onWheel = (event: WheelEvent): void => {
    // Plain scrolling stays with the page. Zoom needs Ctrl or Cmd (a trackpad pinch sends exactly that).
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    this.zoomBy(Math.exp(-event.deltaY * 0.01));
  };

  private readonly onContextLost = (event: Event): void => {
    event.preventDefault();
    this.callbacks.onContextLost();
  };

  private readonly onVisibilityChange = (): void => {
    if (!document.hidden) this.invalidate();
  };

  private readonly onResize = (): void => {
    if (this.disposed) return;
    this.resize();
    this.invalidate();
  };

  // ---- teardown ------------------------------------------------------------

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.frame = 0;

    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointerdown", this.onPointerDown);
    canvas.removeEventListener("pointermove", this.onPointerMove);
    canvas.removeEventListener("pointerup", this.onPointerUp);
    canvas.removeEventListener("pointercancel", this.onPointerCancel);
    canvas.removeEventListener("pointerleave", this.onPointerLeave);
    canvas.removeEventListener("wheel", this.onWheel);
    canvas.removeEventListener("webglcontextlost", this.onContextLost);
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
    window.removeEventListener("resize", this.onResize);
    this.resizeObserver.disconnect();

    this.scene.clear();
    this.segments = [];
    this.labels = [];
    this.overlay.replaceChildren();

    for (const geometry of [this.box, this.boxEdges, this.limitPlane, this.limitEdges, this.floorPlane, this.tickGeometry]) geometry?.dispose();
    for (const set of Object.values(this.materials)) for (const material of Object.values(set)) (material as Material).dispose();
    for (const material of [
      this.fundEdgeMaterial,
      this.unresolvedEdgeMaterial,
      this.limitMaterial,
      this.limitEdgeMaterial,
      this.draftLimitEdgeMaterial,
      this.floorMaterial,
      this.tickMaterial,
    ]) {
      material.dispose();
    }

    this.renderer.dispose();
    this.renderer.forceContextLoss();
    canvas.remove();
  }
}

export default function ExposureScene({ model, labels, selectedId, onSelect, onFailure, ref }: ExposureSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const engineRef = useRef<SceneEngine | null>(null);
  const callbacksRef = useRef({ onSelect, onFailure });

  useEffect(() => {
    callbacksRef.current = { onSelect, onFailure };
  }, [onSelect, onFailure]);

  // Create once, dispose on unmount.
  useEffect(() => {
    const host = hostRef.current;
    const overlay = overlayRef.current;
    if (!host || !overlay) return;
    let engine: SceneEngine;
    try {
      engine = new SceneEngine(host, overlay, {
        onSelect: (id) => callbacksRef.current.onSelect(id),
        onContextLost: () => callbacksRef.current.onFailure("CONTEXT_LOST"),
      });
    } catch {
      callbacksRef.current.onFailure("INIT_FAILED");
      return;
    }
    engineRef.current = engine;
    return () => {
      engineRef.current = null;
      engine.dispose();
    };
  }, []);

  useEffect(() => {
    engineRef.current?.setModel(model, labels);
  }, [model, labels]);

  useEffect(() => {
    engineRef.current?.setSelection(selectedId);
  }, [selectedId]);

  useImperativeHandle(
    ref,
    () => ({
      rotate: (direction) => engineRef.current?.rotateBy(direction * ROTATE_STEP),
      zoom: (direction) => engineRef.current?.zoomBy(direction > 0 ? ZOOM_STEP : 1 / ZOOM_STEP),
      reset: () => engineRef.current?.resetView(),
    }),
    [],
  );

  return (
    <div className="relative h-[22rem] w-full overflow-hidden rounded-md border border-line bg-surface" data-testid="explorer-scene">
      <div ref={hostRef} className="absolute inset-0" />
      {/* Labels are HTML placed over the drawing. They repeat what the table says, so they are hidden from assistive technology. */}
      <div ref={overlayRef} className="pointer-events-none absolute inset-0" aria-hidden="true" />
    </div>
  );
}
