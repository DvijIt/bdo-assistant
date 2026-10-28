"use client";

import Link from "next/link";
import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { API } from "../_lib/api";

type MapNode = {
  node_id: number;
  name: string;
  territory: string | null;
  sub: boolean;
  invested: boolean;
  x: number;
  y: number;
};

type MapKnowledge = { knowledge_id: number; name: string; category: string; acquisition: string | null };

type MapNpc = {
  npc_id: number;
  name: string;
  title: string | null;
  region: string | null;
  x: number;
  y: number;
  knowledge: MapKnowledge[];
};

type MapData = { image: { width: number; height: number }; nodes: MapNode[]; npcs: MapNpc[] } | null;

type Selection = { kind: "node"; node: MapNode } | { kind: "npc"; npc: MapNpc };

const MIN_SCALE = 0.04;
const MAX_SCALE = 1.5;
const ZOOM_STEP = 1.25;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

export default function MapPage() {
  const { data, loaded, error, reload } = useApiData<MapData>("/api/map");
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [view, setView] = useState<{ scale: number; x: number; y: number } | null>(null);
  const [layers, setLayers] = useState({ invested: true, other: false, npcs: true });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [query, setQuery] = useState("");

  // Карта вписується в ширину вікна при першому показі.
  useEffect(() => {
    if (!data || view || !viewport.current) return;
    const { clientWidth, clientHeight } = viewport.current;
    const scale = clamp(Math.min(clientWidth / data.image.width, clientHeight / data.image.height), MIN_SCALE, MAX_SCALE);
    setView({ scale, x: (clientWidth - data.image.width * scale) / 2, y: (clientHeight - data.image.height * scale) / 2 });
  }, [data, view]);

  const matches = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!data || text.length < 2) return [];
    const npcs = data.npcs.filter(
      (npc) => npc.name.toLowerCase().includes(text) || npc.knowledge.some((k) => k.name.toLowerCase().includes(text)),
    );
    const nodes = data.nodes.filter((node) => node.name.toLowerCase().includes(text));
    return [
      ...npcs.map((npc): Selection => ({ kind: "npc", npc })),
      ...nodes.map((node): Selection => ({ kind: "node", node })),
    ].slice(0, 8);
  }, [data, query]);

  function zoomAt(factor: number, cx: number, cy: number) {
    setView((current) => {
      if (!current) return current;
      const scale = clamp(current.scale * factor, MIN_SCALE, MAX_SCALE);
      const ratio = scale / current.scale;
      return { scale, x: cx - (cx - current.x) * ratio, y: cy - (cy - current.y) * ratio };
    });
  }

  function zoomCenter(factor: number) {
    const box = viewport.current;
    if (box) zoomAt(factor, box.clientWidth / 2, box.clientHeight / 2);
  }

  function focus(target: Selection) {
    const point = target.kind === "npc" ? target.npc : target.node;
    const box = viewport.current;
    setSelection(target);
    setQuery("");
    if (target.kind === "node" && !target.node.invested) setLayers((l) => ({ ...l, other: true }));
    if (!box) return;
    const scale = Math.max(view?.scale ?? 0, 0.6);
    setView({ scale, x: box.clientWidth / 2 - point.x * scale, y: box.clientHeight / 2 - point.y * scale });
  }

  // Колесо слухаємо напряму з passive: false, інакше разом із масштабом гортається й сторінка.
  useEffect(() => {
    const box = viewport.current;
    if (!box) return;
    function onWheel(event: globalThis.WheelEvent) {
      event.preventDefault();
      const rect = box!.getBoundingClientRect();
      zoomAt(event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP, event.clientX - rect.left, event.clientY - rect.top);
    }
    box.addEventListener("wheel", onWheel, { passive: false });
    return () => box.removeEventListener("wheel", onWheel);
  }, [data]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    drag.current = { x: event.clientX, y: event.clientY, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    drag.current = { x: event.clientX, y: event.clientY, moved: true };
    setView((current) => (current ? { ...current, x: current.x + dx, y: current.y + dy } : current));
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current;
    drag.current = null;
    // Клік без перетягування по маркеру вибирає його.
    if (start && !start.moved) {
      const target = (event.target as HTMLElement).closest<HTMLElement>("[data-marker]");
      if (!target || !data) return;
      const [kind, id] = target.dataset.marker!.split(":");
      if (kind === "npc") {
        const npc = data.npcs.find((n) => n.npc_id === Number(id));
        if (npc) setSelection({ kind: "npc", npc });
      } else {
        const node = data.nodes.find((n) => n.node_id === Number(id));
        if (node) setSelection({ kind: "node", node });
      }
    }
  }

  const nodes = (data?.nodes ?? []).filter((node) => (node.invested ? layers.invested : layers.other));
  const npcs = layers.npcs ? data?.npcs ?? [] : [];
  const selectedId = selection?.kind === "npc" ? `npc:${selection.npc.npc_id}` : selection ? `node:${selection.node.node_id}` : "";

  return (
    <AccountPage
      title="Карта"
      subtitle="Карта регіонів з твого клієнта гри: вкладені вузли й NPC, у яких можна взяти ще не зібрані знання. Колесо миші — масштаб, перетягування — рух."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {loaded && data === null ? (
        <EmptyState title="Карти ще немає">
          З закритою грою згенеруй її в папці extractor:{" "}
          <code>go run . regionmaps --game D:\BlackDesert --out D:\Projects\bdo-data</code>, а потім повтори імпорт на
          сторінці <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        data && (
          <>
            <div className="map-toolbar">
              <div className="map-layers" role="group" aria-label="Шари карти">
                <label>
                  <input type="checkbox" checked={layers.invested} onChange={(e) => setLayers({ ...layers, invested: e.target.checked })} />
                  <span className="map-swatch invested" /> Вкладені вузли ({data.nodes.filter((n) => n.invested).length})
                </label>
                <label>
                  <input type="checkbox" checked={layers.other} onChange={(e) => setLayers({ ...layers, other: e.target.checked })} />
                  <span className="map-swatch other" /> Інші вузли
                </label>
                <label>
                  <input type="checkbox" checked={layers.npcs} onChange={(e) => setLayers({ ...layers, npcs: e.target.checked })} />
                  <span className="map-swatch npc" /> NPC з незібраними знаннями ({data.npcs.length})
                </label>
              </div>
              <div className="map-search">
                <input
                  type="search"
                  placeholder="Знайти NPC, знання чи вузол…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Пошук на карті"
                />
                {matches.length > 0 && (
                  <ul className="map-matches">
                    {matches.map((match) => (
                      <li key={match.kind === "npc" ? `npc-${match.npc.npc_id}` : `node-${match.node.node_id}`}>
                        <button type="button" onClick={() => focus(match)}>
                          <strong>{match.kind === "npc" ? match.npc.name : match.node.name}</strong>
                          <span>
                            {match.kind === "npc"
                              ? `${match.npc.region ?? "NPC"} · ${match.npc.knowledge.length} знань`
                              : `${match.node.territory ?? "Вузол"}${match.node.invested ? " · вкладено" : ""}`}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="map-layout">
              <div
                className="map-viewport"
                ref={viewport}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={() => (drag.current = null)}
              >
                {view && (
                  <div
                    className="map-canvas"
                    style={{
                      width: data.image.width,
                      height: data.image.height,
                      transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
                      // Маркери тримають однаковий розмір на екрані за будь-якого масштабу.
                      ["--marker-scale" as string]: String(1 / view.scale),
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- величезна локальна картинка, оптимізація Next тут не допоможе */}
                    <img src={`${API}/api/game-data/map-image`} alt="" width={data.image.width} height={data.image.height} draggable={false} />
                    {nodes.map((node) => (
                      <span
                        key={`node-${node.node_id}`}
                        data-marker={`node:${node.node_id}`}
                        className={`map-marker node${node.invested ? " invested" : ""}${node.sub ? " sub" : ""}${selectedId === `node:${node.node_id}` ? " selected" : ""}`}
                        style={{ left: node.x, top: node.y }}
                        title={node.name}
                      />
                    ))}
                    {npcs.map((npc) => (
                      <span
                        key={`npc-${npc.npc_id}`}
                        data-marker={`npc:${npc.npc_id}`}
                        className={`map-marker npc${selectedId === `npc:${npc.npc_id}` ? " selected" : ""}`}
                        style={{ left: npc.x, top: npc.y }}
                        title={`${npc.name} — ${npc.knowledge.length} знань`}
                      />
                    ))}
                  </div>
                )}
                <div className="map-zoom">
                  <button type="button" className="outline-button" onClick={() => zoomCenter(ZOOM_STEP)} aria-label="Наблизити">+</button>
                  <button type="button" className="outline-button" onClick={() => zoomCenter(1 / ZOOM_STEP)} aria-label="Віддалити">−</button>
                  <button type="button" className="outline-button" onClick={() => setView(null)}>Уся карта</button>
                </div>
              </div>

              <aside className="panel map-details">
                {!selection ? (
                  <p className="inventory-muted">
                    Натисни на маркер, щоб побачити, що там. Сині точки — NPC, у яких можна взяти знання, яких у тебе ще
                    немає; золоті — вкладені вузли.
                  </p>
                ) : selection.kind === "npc" ? (
                  <>
                    <div className="eyebrow">{selection.npc.region ?? "NPC"}</div>
                    <h2>{selection.npc.name}</h2>
                    {selection.npc.title && <p className="inventory-muted">{selection.npc.title}</p>}
                    <div className="eyebrow snapshot-list-title">НЕ ЗІБРАНІ ЗНАННЯ</div>
                    <ul className="snapshot-list">
                      {selection.npc.knowledge.map((k) => (
                        <li key={k.knowledge_id}>
                          <strong>{k.name}</strong>
                          <span>{k.category}</span>
                          {k.acquisition && k.acquisition !== k.name && <span className="map-hint">{k.acquisition}</span>}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : (
                  <>
                    <div className="eyebrow">{selection.node.territory ?? "ВУЗОЛ"}</div>
                    <h2>{selection.node.name}</h2>
                    <p className="inventory-muted">
                      {selection.node.invested ? "Очки внеску вкладено." : "Не вкладено."}
                      {selection.node.sub ? " Підвузол." : ""}
                    </p>
                    <Link className="text-link" href="/nodes/">Усі вкладені вузли →</Link>
                  </>
                )}
              </aside>
            </div>
          </>
        )
      )}
    </AccountPage>
  );
}
