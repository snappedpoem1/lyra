import { useEffect, useMemo, useState } from "react";
import type { ConstellationEdge, ConstellationNode } from "@/types/domain";
import { LyraPanel } from "@/ui/LyraPanel";

function layout(nodes: ConstellationNode[]): ConstellationNode[] {
  const centerX = 320;
  const centerY = 190;
  return nodes.map((node, index) => {
    if (index === 0) {
      return { ...node, x: centerX, y: centerY };
    }
    const ring = Math.floor((index + 2) / 2);
    const angle = 0.9 + index * 1.37;
    const radius = 90 + ring * 74;
    return {
      ...node,
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius * 0.72,
    };
  });
}

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

  useEffect(() => {
    let frame = 0;
    let animationId = 0;
    const loop = () => {
      frame += 1;
      setTick(frame);
      animationId = window.requestAnimationFrame(loop);
    };
    animationId = window.requestAnimationFrame(loop);
    return () => window.cancelAnimationFrame(animationId);
  }, []);

  const laidOut = useMemo(() => layout(nodes), [nodes]);
  const lookup = useMemo(() => new Map(laidOut.map((node) => [node.id, node])), [laidOut]);
  const focusNode = laidOut.find((node) => node.id === focusNodeId) ?? laidOut[0];
  const relatedEdges = edges.filter((edge) => edge.source === focusNode?.id || edge.target === focusNode?.id);
  const stars = useMemo(
    () =>
      Array.from({ length: 72 }, (_, index) => ({
        id: `star-${index}`,
        x: 20 + ((index * 71) % 600),
        y: 18 + ((index * 53) % 380),
        r: 0.5 + ((index % 5) * 0.35),
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
              fill={node.accent ?? "#f0a44b"}
              fillOpacity={focusNodeId === node.id ? 0.26 : 0.12 + node.weight * 0.12}
            />
            <circle r={5 + node.weight * 6} fill={node.accent ?? "#f0a44b"} />
            <circle r={1.6 + node.weight * 2.3} fill="#fff5e0" />
            <text y={36} textAnchor="middle" fill="#f3e5d0" fontSize="12">{node.label}</text>
          </g>
        ))}
      </svg>
      <div className="constellation-focus">
        <div>
          <span className="insight-kicker">Selected</span>
          <strong>{focusNode?.label ?? "Click a node to inspect"}</strong>
          <p>{relatedEdges[0]?.reason ?? "Select a node to see how it connects to the rest of your library."}</p>
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
