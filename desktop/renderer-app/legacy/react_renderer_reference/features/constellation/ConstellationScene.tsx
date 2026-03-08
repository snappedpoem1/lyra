import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ConstellationEdge, ConstellationNode } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";
import { resolveApiUrl } from "@/services/lyraGateway/client";

// ---------------------------------------------------------------------------
// Force-directed simulation constants
// ---------------------------------------------------------------------------
const SVG_W = 640;
const SVG_H = 420;
const CX = SVG_W / 2;
const CY = SVG_H / 2;

const REPULSION = 3400;
const SPRING_K = 0.032;
const SPRING_REST = 138;
const GRAVITY = 0.022;
const DAMPING = 0.80;
const DT = 0.85;
// Simulation decays to near-still after ~120 frames; keep ticking gently after.
const SIM_HOT_FRAMES = 120;

type Vec2 = { x: number; y: number };

function seedPositions(nodes: ConstellationNode[]): Map<string, Vec2> {
  const pos = new Map<string, Vec2>();
  nodes.forEach((node, i) => {
    if (i === 0) {
      pos.set(node.id, { x: CX, y: CY });
    } else {
      const angle = (i / nodes.length) * Math.PI * 2;
      const r = 80 + (i % 3) * 68;
      pos.set(node.id, {
        x: CX + Math.cos(angle) * r,
        y: CY + Math.sin(angle) * r * 0.72,
      });
    }
  });
  return pos;
}

function seedVelocities(nodes: ConstellationNode[]): Map<string, Vec2> {
  const vel = new Map<string, Vec2>();
  nodes.forEach((n) => vel.set(n.id, { x: 0, y: 0 }));
  return vel;
}

function simStep(
  nodes: ConstellationNode[],
  edges: ConstellationEdge[],
  pos: Map<string, Vec2>,
  vel: Map<string, Vec2>,
): void {
  const force = new Map<string, Vec2>();
  nodes.forEach((n) => force.set(n.id, { x: 0, y: 0 }));

  // Repulsion: every node pair (O(n²) but n is small — typically < 80 nodes)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = pos.get(nodes[i].id)!;
      const b = pos.get(nodes[j].id)!;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist2 = dx * dx + dy * dy + 1;
      const dist = Math.sqrt(dist2);
      const mag = REPULSION / dist2;
      const fx = (dx / dist) * mag;
      const fy = (dy / dist) * mag;
      const fa = force.get(nodes[i].id)!;
      const fb = force.get(nodes[j].id)!;
      fa.x += fx; fa.y += fy;
      fb.x -= fx; fb.y -= fy;
    }
  }

  // Spring attraction along edges
  for (const edge of edges) {
    const a = pos.get(edge.source);
    const b = pos.get(edge.target);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
    const rest = SPRING_REST * (1 - edge.strength * 0.28);
    const stretch = dist - rest;
    const f = SPRING_K * stretch;
    const fx = (dx / dist) * f;
    const fy = (dy / dist) * f;
    const fa = force.get(edge.source);
    const fb = force.get(edge.target);
    if (fa) { fa.x += fx; fa.y += fy; }
    if (fb) { fb.x -= fx; fb.y -= fy; }
  }

  // Centre gravity — pulls all nodes toward the SVG centre
  nodes.forEach((n) => {
    const p = pos.get(n.id)!;
    const f = force.get(n.id)!;
    f.x += (CX - p.x) * GRAVITY;
    f.y += (CY - p.y) * GRAVITY;
  });

  // Velocity integration + soft-wall boundary clamping
  nodes.forEach((n) => {
    const p = pos.get(n.id)!;
    const v = vel.get(n.id)!;
    const f = force.get(n.id)!;
    v.x = (v.x + f.x * DT) * DAMPING;
    v.y = (v.y + f.y * DT) * DAMPING;
    pos.set(n.id, {
      x: Math.max(44, Math.min(SVG_W - 44, p.x + v.x)),
      y: Math.max(28, Math.min(SVG_H - 28, p.y + v.y)),
    });
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function ConstellationScene({
  nodes,
  edges,
  onSelectNode,
}: {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
  onSelectNode: (node: ConstellationNode) => void;
}) {
  const [focusNodeId, setFocusNodeId] = useState<string | null>(nodes[0]?.id ?? null);
  const [tick, setTick] = useState(0);
  const [acquiring, setAcquiring] = useState<string | null>(null);
  const [acquireStatus, setAcquireStatus] = useState<"idle" | "queued" | "error">("idle");

  // Simulation state lives in refs — no re-render until setTick fires
  const posRef = useRef<Map<string, Vec2>>(new Map());
  const velRef = useRef<Map<string, Vec2>>(new Map());
  const simFrameRef = useRef(0);

  // Re-seed simulation whenever the node list identity changes
  const nodeIds = nodes.map((n) => n.id).join(",");
  useEffect(() => {
    posRef.current = seedPositions(nodes);
    velRef.current = seedVelocities(nodes);
    simFrameRef.current = 0;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeIds]);

  // Animation + simulation loop
  useEffect(() => {
    let frame = 0;
    let animId = 0;
    const loop = () => {
      frame += 1;
      // Run more sim steps while still hot; 1 step per frame once settled
      const steps = simFrameRef.current < SIM_HOT_FRAMES ? 3 : 1;
      for (let s = 0; s < steps; s++) {
        simStep(nodes, edges, posRef.current, velRef.current);
      }
      simFrameRef.current += steps;
      setTick(frame);
      animId = window.requestAnimationFrame(loop);
    };
    animId = window.requestAnimationFrame(loop);
    return () => window.cancelAnimationFrame(animId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeIds]);

  const handleAcquireArtist = useCallback(async (label: string) => {
    setAcquiring(label);
    setAcquireStatus("idle");
    try {
      const resp = await fetch(resolveApiUrl("/api/acquire/batch"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queries: [label], workers: 2 }),
      });
      setAcquireStatus(resp.ok ? "queued" : "error");
    } catch {
      setAcquireStatus("error");
    } finally {
      setAcquiring(null);
    }
  }, []);

  // Derive positioned nodes from simulation state for render
  const laidOut = useMemo(
    () =>
      nodes.map((node) => {
        const p = posRef.current.get(node.id) ?? { x: CX, y: CY };
        return { ...node, x: p.x, y: p.y };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick, nodeIds],
  );

  const lookup = useMemo(() => new Map(laidOut.map((n) => [n.id, n])), [laidOut]);
  const focusNode = laidOut.find((n) => n.id === focusNodeId) ?? laidOut[0];
  const relatedEdges = edges.filter((e) => e.source === focusNode?.id || e.target === focusNode?.id);

  const stars = useMemo(
    () =>
      Array.from({ length: 72 }, (_, i) => ({
        id: `star-${i}`,
        x: 20 + ((i * 71) % 600),
        y: 18 + ((i * 53) % 380),
        r: 0.5 + ((i % 5) * 0.35),
      })),
    [],
  );

  return (
    <LyraPanel className="constellation-panel">
      <div className="section-heading">
        <h2>Taste map</h2>
        <span>Connections between tracks, artists, and moods</span>
      </div>
      <svg viewBox="0 0 640 420" className="constellation-svg">
        <defs>
          <radialGradient id="constellation-core" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="rgba(255,216,168,0.6)" />
            <stop offset="70%" stopColor="rgba(255,150,64,0.12)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0)" />
          </radialGradient>
        </defs>
        <rect width="640" height="420" fill="transparent" />
        {stars.map((star) => (
          <circle
            key={star.id}
            cx={star.x + Math.sin((tick + star.x) / 180) * 2}
            cy={star.y + Math.cos((tick + star.y) / 190) * 2}
            r={star.r}
            fill="rgba(255, 236, 208, 0.6)"
          />
        ))}
        {focusNode && <circle cx={focusNode.x} cy={focusNode.y} r="150" fill="url(#constellation-core)" />}
        {edges.map((edge) => {
          const source = lookup.get(edge.source);
          const target = lookup.get(edge.target);
          if (!source || !target) return null;
          const isFocused = edge.source === focusNode?.id || edge.target === focusNode?.id;
          return (
            <line
              key={edge.id}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={isFocused ? "rgba(255, 221, 175, 0.52)" : "rgba(255, 206, 150, 0.14)"}
              strokeWidth={isFocused ? 2.6 + edge.strength * 2.4 : 0.8 + edge.strength * 1.6}
            />
          );
        })}
        {laidOut.map((node) => (
          <g
            key={node.id}
            transform={`translate(${node.x}, ${node.y})`}
            onClick={() => {
              setFocusNodeId(node.id);
              onSelectNode(node);
            }}
            style={{ cursor: "pointer" }}
          >
            <circle
              r={18 + node.weight * 16 + (focusNodeId === node.id ? 6 : 0)}
              fill={node.inLibrary !== false ? (node.accent ?? "#f0a44b") : "#8896aa"}
              fillOpacity={focusNodeId === node.id ? 0.26 : node.inLibrary !== false ? 0.12 + node.weight * 0.12 : 0.05}
            />
            <circle r={5 + node.weight * 6} fill={node.inLibrary !== false ? (node.accent ?? "#f0a44b") : "#8896aa"} />
            <circle r={1.6 + node.weight * 2.3} fill={node.inLibrary !== false ? "#fff5e0" : "#aabbcc"} />
            <text y={36} textAnchor="middle" fill="#f3e5d0" fontSize="12">{node.label}</text>
          </g>
        ))}
      </svg>
      <div className="constellation-focus">
        <div>
          <span className="insight-kicker">Selected</span>
          <strong>{focusNode?.label ?? "Click a node to inspect"}</strong>
          <p>{relatedEdges[0]?.reason ?? "Select a node to see how it connects to the rest of your library."}</p>
          {focusNode && !focusNode.inLibrary && (
            <div className="constellation-acquire-cta">
              <span className="insight-kicker" style={{ color: "#8896aa" }}>Not in your library</span>
              {acquireStatus === "queued" ? (
                <span style={{ fontSize: 12, color: "#6dbb8a" }}>Queued for acquisition ✓</span>
              ) : acquireStatus === "error" ? (
                <span style={{ fontSize: 12, color: "#cc7a7a" }}>Acquisition failed — try again</span>
              ) : (
                <button
                  className="lyra-btn lyra-btn--ghost lyra-btn--sm"
                  disabled={acquiring === focusNode.label}
                  onClick={() => handleAcquireArtist(focusNode.label)}
                >
                  {acquiring === focusNode.label ? "Queuing…" : `Scout ${focusNode.label}`}
                </button>
              )}
            </div>
          )}
        </div>
        <div className="constellation-legend">
          {relatedEdges.slice(0, 3).map((edge) => (
            <div key={edge.id} className="constellation-legend-row">
              <span>{edge.relationship}</span>
              <strong>{edge.reason ?? "Related by similarity"}</strong>
            </div>
          ))}
        </div>
      </div>
    </LyraPanel>
  );
}
