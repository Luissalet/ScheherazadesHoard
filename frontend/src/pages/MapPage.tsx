import { useEffect, useMemo, useRef, useState } from "react";
import { Network } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { Lang } from "../lib/i18n";
import { t } from "../lib/i18n";
import type { Entity, Relation, World } from "../lib/types";
import { EmptyState, ErrorBanner } from "../components/ui";

interface Point {
  x: number;
  y: number;
}

/** Simple deterministic circular layout — no physics dependency, no network. */
function layout(entities: Entity[], width: number, height: number): Record<string, Point> {
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.max(60, Math.min(cx, cy) - 60);
  const positions: Record<string, Point> = {};
  entities.forEach((e, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, entities.length) - Math.PI / 2;
    positions[e.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });
  return positions;
}

const KIND_COLOR: Record<string, string> = {
  character: "var(--accent)",
  location: "var(--gold)",
  faction: "#a4508b",
  item: "#4a8b6f",
  lore: "#6b7bb8",
  creature: "#b85c4a",
};

export function MapPage({ world, lang }: { world: World; lang: Lang }) {
  const [entities, setEntities] = useState<Entity[] | null>(null);
  const [relations, setRelations] = useState<Relation[] | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 800, height: 520 });

  useEffect(() => {
    setEntities(null);
    setRelations(null);
    Promise.all([api.listEntities(world.id), api.listRelations(world.id)])
      .then(([e, r]) => {
        setEntities(e);
        setRelations(r);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [world.id]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entriesList) => {
      const box = entriesList[0]?.contentRect;
      if (box) setSize({ width: Math.max(400, box.width), height: Math.max(360, box.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const positions = useMemo(
    () => layout(entities ?? [], size.width, size.height),
    [entities, size.width, size.height],
  );

  const byId = useMemo(() => {
    const m: Record<string, Entity> = {};
    (entities ?? []).forEach((e) => { m[e.id] = e; });
    return m;
  }, [entities]);

  if (error) return <ErrorBanner message={error} />;
  if (entities === null) return <p>{t("loading", lang)}</p>;
  if (entities.length === 0) {
    return <EmptyState icon={<Network size={28} />}>{t("bible_empty", lang)}</EmptyState>;
  }

  return (
    <div className="card" style={{ height: "100%", padding: 0, overflow: "hidden" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative" }}>
        <svg width={size.width} height={size.height} style={{ display: "block" }}>
          {(relations ?? []).map((rel) => {
            const a = positions[rel.a_id];
            const b = positions[rel.b_id];
            if (!a || !b) return null;
            const active = hovered === rel.a_id || hovered === rel.b_id;
            return (
              <g key={rel.id}>
                <line
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={active ? "var(--accent)" : "var(--border)"}
                  strokeWidth={active ? 2 : 1}
                />
                <text
                  x={(a.x + b.x) / 2}
                  y={(a.y + b.y) / 2}
                  fontSize={10}
                  fill="var(--text-muted)"
                  textAnchor="middle"
                >
                  {rel.type}
                </text>
              </g>
            );
          })}
          {entities.map((e) => {
            const p = positions[e.id];
            if (!p) return null;
            return (
              <g
                key={e.id}
                transform={`translate(${p.x}, ${p.y})`}
                onMouseEnter={() => setHovered(e.id)}
                onMouseLeave={() => setHovered((h) => (h === e.id ? null : h))}
                style={{ cursor: "default" }}
              >
                <circle r={hovered === e.id ? 12 : 9} fill={KIND_COLOR[e.kind] ?? "var(--accent)"} opacity={0.85} />
                <text y={22} fontSize={11} textAnchor="middle" fill="var(--text)">
                  {e.name}
                </text>
              </g>
            );
          })}
        </svg>
        {hovered && byId[hovered] && (
          <div
            className="card"
            style={{ position: "absolute", top: 12, right: 12, maxWidth: 240, pointerEvents: "none" }}
          >
            <strong style={{ fontSize: 13 }}>{byId[hovered].name}</strong>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-muted)" }}>{byId[hovered].summary}</p>
          </div>
        )}
      </div>
    </div>
  );
}
