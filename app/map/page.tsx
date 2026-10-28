"use client";

import Link from "next/link";
import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { AccountPage, EmptyState, useApiData } from "../_components/AccountPage";
import { API } from "../_lib/api";

type Layer = {
  name: string;
  tilePx: number;
  unitsPerPixel: number;
  unitsPerTile: number;
  maxZoom: number;
  grid: { xmin: number; xmax: number; ymin: number; ymax: number };
  oceanColor?: [number, number, number];
};

type MapNode = {
  node_id: number;
  name: string;
  territory: string | null;
  sub: boolean;
  invested: boolean;
  layer: string;
  x: number;
  z: number;
};

type MapKnowledge = { knowledge_id: number; name: string; category: string; acquisition: string | null };

type MapNpc = {
  npc_id: number;
  name: string;
  title: string | null;
  region: string | null;
  layer: string;
  x: number;
  z: number;
  knowledge: MapKnowledge[];
};

type MapSpot = {
  spot_id: number;
  name: string;
  region: string | null;
  sheet_ap: number | null;
  sheet_dp: number | null;
  layer: string;
  x: number;
  z: number;
};

type MapData = { layers: Layer[]; grind: MapSpot[]; nodes: MapNode[]; npcs: MapNpc[] } | null;

type GrindStatus = "ok" | "close" | "low" | "unknown";

type Grind = { gear: { ap: number | null; dp: number | null }; spots: { spot_id: number; status: GrindStatus }[] };

type Selection = { kind: "node"; node: MapNode } | { kind: "npc"; npc: MapNpc } | { kind: "spot"; spot: MapSpot };

const GRIND_LABELS: Record<GrindStatus, string> = {
  ok: "AP/DP підходять",
  close: "Трохи не вистачає AP/DP",
  low: "Заслабко",
  unknown: "Свої AP/DP введи на сторінці «Гринд»",
};

// Вид: масштаб — екранних пікселів на піксель найдетальнішого рівня плиток; x, y — зсув.
type View = { scale: number; x: number; y: number };

const ZOOM_STEP = 1.5;
const MAX_SCALE = 2;
const LAYER_LABELS: Record<string, string> = { world: "Світ", morningland: "Ранкова Країна" };

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/** Точка світу (x, z) у пікселях найдетальнішого рівня: схід праворуч, північ угорі. */
function toMap(layer: Layer, x: number, z: number) {
  return { px: x / layer.unitsPerPixel, py: -z / layer.unitsPerPixel };
}

/** Межі карти шару в пікселях найдетальнішого рівня. */
function bounds(layer: Layer) {
  const { grid, tilePx } = layer;
  return { left: grid.xmin * tilePx, right: (grid.xmax + 1) * tilePx, top: -(grid.ymax + 1) * tilePx, bottom: -grid.ymin * tilePx };
}

export default function MapPage() {
  const { data, loaded, error, reload } = useApiData<MapData>("/api/map");
  const grind = useApiData<Grind>("/api/grind");
  const grindStatus = new Map((grind.data?.spots ?? []).map((s) => [s.spot_id, s.status]));
  const focused = useRef(false);
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean; pointer: number } | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [layerName, setLayerName] = useState("world");
  const [view, setView] = useState<View | null>(null);
  const [layers, setLayers] = useState({ invested: true, other: false, npcs: true, grind: true });
  const [selection, setSelection] = useState<Selection | null>(null);
  const [query, setQuery] = useState("");

  const layer = data?.layers.find((l) => l.name === layerName) ?? data?.layers[0];

  // Розмір вікна карти стежимо постійно: від нього залежать видимі плитки.
  useEffect(() => {
    const box = viewport.current;
    if (!box) return;
    const observer = new ResizeObserver(() => setSize({ width: box.clientWidth, height: box.clientHeight }));
    observer.observe(box);
    return () => observer.disconnect();
  }, [data]);

  function fit(target: Layer): View {
    const b = bounds(target);
    const scale = Math.min(size.width / (b.right - b.left), size.height / (b.bottom - b.top));
    return {
      scale,
      x: (size.width - (b.right - b.left) * scale) / 2 - b.left * scale,
      y: (size.height - (b.bottom - b.top) * scale) / 2 - b.top * scale,
    };
  }

  // Без власного виду (перший показ, інший шар, «Уся карта») показуємо весь шар.
  const shown = view ?? (layer && size.width ? fit(layer) : null);

  function zoomAt(factor: number, cx: number, cy: number) {
    setView((saved) => {
      const current = saved ?? shown;
      if (!current || !layer) return saved;
      const minScale = fit(layer).scale / 2;
      const scale = clamp(current.scale * factor, minScale, MAX_SCALE);
      const ratio = scale / current.scale;
      return { scale, x: cx - (cx - current.x) * ratio, y: cy - (cy - current.y) * ratio };
    });
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
  });

  const matches = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!data || text.length < 2) return [];
    const npcs = data.npcs.filter(
      (npc) => npc.name.toLowerCase().includes(text) || npc.knowledge.some((k) => k.name.toLowerCase().includes(text)),
    );
    const nodes = data.nodes.filter((node) => node.name.toLowerCase().includes(text));
    const spots = data.grind.filter((spot) => spot.name.toLowerCase().includes(text));
    return [
      ...spots.map((spot): Selection => ({ kind: "spot", spot })),
      ...npcs.map((npc): Selection => ({ kind: "npc", npc })),
      ...nodes.map((node): Selection => ({ kind: "node", node })),
    ].slice(0, 8);
  }, [data, query]);

  function focus(target: Selection) {
    const point = target.kind === "npc" ? target.npc : target.kind === "spot" ? target.spot : target.node;
    const targetLayer = data?.layers.find((l) => l.name === point.layer);
    setSelection(target);
    setQuery("");
    if (target.kind === "node" && !target.node.invested) setLayers((l) => ({ ...l, other: true }));
    if (target.kind === "npc") setLayers((l) => ({ ...l, npcs: true }));
    if (target.kind === "spot") setLayers((l) => ({ ...l, grind: true }));
    if (!targetLayer) return;
    setLayerName(targetLayer.name);
    const { px, py } = toMap(targetLayer, point.x, point.z);
    const scale = Math.max(shown?.scale ?? 0, 0.5);
    setView({ scale, x: size.width / 2 - px * scale, y: size.height / 2 - py * scale });
  }

  // Посилання /map/?spot=… (зі сторінки «Гринд») показує це місце, щойно відомий розмір карти.
  useEffect(() => {
    if (focused.current || !data || !size.width) return;
    focused.current = true;
    const id = Number(new URLSearchParams(window.location.search).get("spot"));
    const spot = data.grind.find((s) => s.spot_id === id);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- один раз після першого виміру карти; адреса є лише в браузері
    if (spot) focus({ kind: "spot", spot });
  });

  function switchLayer(name: string) {
    setLayerName(name);
    setView(null);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    // Кнопки й маркери обробляють клік самі; тягнемо лише за саму карту.
    if ((event.target as HTMLElement).closest("button, [data-marker]")) return;
    drag.current = { x: event.clientX, y: event.clientY, moved: false, pointer: event.pointerId };
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (!start.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    if (!start.moved) event.currentTarget.setPointerCapture(start.pointer);
    drag.current = { ...start, x: event.clientX, y: event.clientY, moved: true };
    setView((saved) => {
      const current = saved ?? shown;
      return current ? { ...current, x: current.x + dx, y: current.y + dy } : saved;
    });
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (drag.current?.moved) event.currentTarget.releasePointerCapture(drag.current.pointer);
    drag.current = null;
  }

  // Плитки, що видно зараз: рівень — за масштабом, діапазон — за видимою частиною й сіткою шару.
  const tiles: { key: string; src: string; left: number; top: number; size: number }[] = [];
  if (layer && shown && size.width) {
    const level = clamp(Math.round(layer.maxZoom + Math.log2(shown.scale)), 0, layer.maxZoom);
    const span = 2 ** (layer.maxZoom - level);
    const tileSize = layer.tilePx * span; // у пікселях найдетальнішого рівня
    const g = layer.grid;
    const xmin = Math.max(Math.floor(-shown.x / shown.scale / tileSize), Math.floor(g.xmin / span));
    const xmax = Math.min(Math.floor((size.width - shown.x) / shown.scale / tileSize), Math.floor(g.xmax / span));
    // Плитка y лежить між північним краєм -(y+1)·розмір і південним -y·розмір.
    const ymin = Math.max(Math.floor(-(size.height - shown.y) / shown.scale / tileSize), Math.floor(g.ymin / span));
    const ymax = Math.min(Math.floor(shown.y / shown.scale / tileSize), Math.floor(g.ymax / span));
    for (let tx = xmin; tx <= xmax; tx++) {
      for (let ty = ymin; ty <= ymax; ty++) {
        tiles.push({
          key: `${level}/${tx}/${ty}`,
          src: `${API}/api/game-data/map-tiles/${layer.name}/${level}/${tx}/${ty}`,
          left: shown.x + tx * tileSize * shown.scale,
          top: shown.y - (ty + 1) * tileSize * shown.scale,
          size: tileSize * shown.scale,
        });
      }
    }
  }

  function screen(x: number, z: number) {
    if (!layer || !shown) return null;
    const { px, py } = toMap(layer, x, z);
    const left = shown.x + px * shown.scale;
    const top = shown.y + py * shown.scale;
    return left < -10 || top < -10 || left > size.width + 10 || top > size.height + 10 ? null : { left, top };
  }

  const shownNodes = (data?.nodes ?? []).filter(
    (node) => node.layer === layer?.name && (node.invested ? layers.invested : layers.other),
  );
  const shownNpcs = layers.npcs ? (data?.npcs ?? []).filter((npc) => npc.layer === layer?.name) : [];
  const shownSpots = layers.grind ? (data?.grind ?? []).filter((spot) => spot.layer === layer?.name) : [];
  const selectedKey =
    selection?.kind === "npc" ? `npc:${selection.npc.npc_id}`
      : selection?.kind === "spot" ? `spot:${selection.spot.spot_id}`
        : selection ? `node:${selection.node.node_id}` : "";
  const ocean = layer?.oceanColor ? `rgb(${layer.oceanColor.join(",")})` : undefined;

  return (
    <AccountPage
      title="Карта"
      subtitle="Карта світу з твого клієнта гри: вкладені вузли й NPC, у яких можна взяти ще не зібрані знання. Колесо миші — масштаб, перетягування — рух."
      onRecords={reload}
    >
      {error && <p className="inventory-feedback error">{error}</p>}

      {loaded && data === null ? (
        <EmptyState title="Карти ще немає">
          З закритою грою згенеруй плитки в папці extractor:{" "}
          <code>go run . worldmap-files --game D:\BlackDesert --out D:\Projects\bdo-data</code>. Імпорт повторювати не
          треба — після цього просто онови сторінку. Шлях до папки імпорту видно на сторінці{" "}
          <Link className="text-link" href="/game-data/">«Дані гри»</Link>.
        </EmptyState>
      ) : (
        data &&
        layer && (
          <>
            <div className="map-toolbar">
              <div className="map-layers" role="group" aria-label="Шари карти">
                {data.layers.length > 1 && (
                  <span className="map-tabs">
                    {data.layers.map((l) => (
                      <button
                        key={l.name}
                        type="button"
                        className={l.name === layer.name ? "outline-button active" : "outline-button"}
                        onClick={() => switchLayer(l.name)}
                      >
                        {LAYER_LABELS[l.name] ?? l.name}
                      </button>
                    ))}
                  </span>
                )}
                <label>
                  <input type="checkbox" checked={layers.invested} onChange={(e) => setLayers({ ...layers, invested: e.target.checked })} />
                  <span className="map-swatch invested" /> Вкладені вузли
                </label>
                <label>
                  <input type="checkbox" checked={layers.other} onChange={(e) => setLayers({ ...layers, other: e.target.checked })} />
                  <span className="map-swatch other" /> Інші вузли
                </label>
                <label>
                  <input type="checkbox" checked={layers.grind} onChange={(e) => setLayers({ ...layers, grind: e.target.checked })} />
                  <span className="map-swatch grind" /> Місця для гринду ({data.grind.length})
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
                      <li
                        key={match.kind === "npc" ? `npc-${match.npc.npc_id}` : match.kind === "spot" ? `spot-${match.spot.spot_id}` : `node-${match.node.node_id}`}
                      >
                        <button type="button" onClick={() => focus(match)}>
                          <strong>{match.kind === "npc" ? match.npc.name : match.kind === "spot" ? match.spot.name : match.node.name}</strong>
                          <span>
                            {match.kind === "npc"
                              ? `${match.npc.region ?? "NPC"} · ${match.npc.knowledge.length} знань`
                              : match.kind === "spot"
                                ? `Гринд · ${match.spot.sheet_ap ?? "—"} AP / ${match.spot.sheet_dp ?? "—"} DP`
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
                style={{ background: ocean }}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
              >
                {tiles.map((tile) => (
                  // eslint-disable-next-line @next/next/no-img-element -- тисячі локальних плиток, оптимізація Next тут не допоможе
                  <img
                    key={tile.key}
                    className="map-tile"
                    src={tile.src}
                    alt=""
                    draggable={false}
                    style={{ left: tile.left, top: tile.top, width: tile.size, height: tile.size }}
                  />
                ))}
                {shownNodes.map((node) => {
                  const at = screen(node.x, node.z);
                  if (!at) return null;
                  const key = `node:${node.node_id}`;
                  return (
                    <button
                      key={key}
                      type="button"
                      data-marker={key}
                      className={`map-marker node${node.invested ? " invested" : ""}${node.sub ? " sub" : ""}${selectedKey === key ? " selected" : ""}`}
                      style={at}
                      title={node.name}
                      aria-label={node.name}
                      onClick={() => setSelection({ kind: "node", node })}
                    />
                  );
                })}
                {shownSpots.map((spot) => {
                  const at = screen(spot.x, spot.z);
                  if (!at) return null;
                  const key = `spot:${spot.spot_id}`;
                  const status = grindStatus.get(spot.spot_id) ?? "unknown";
                  return (
                    <button
                      key={key}
                      type="button"
                      data-marker={key}
                      className={`map-marker grind ${status}${selectedKey === key ? " selected" : ""}`}
                      style={at}
                      title={`${spot.name} — ${spot.sheet_ap ?? "—"} AP / ${spot.sheet_dp ?? "—"} DP`}
                      aria-label={spot.name}
                      onClick={() => setSelection({ kind: "spot", spot })}
                    />
                  );
                })}
                {shownNpcs.map((npc) => {
                  const at = screen(npc.x, npc.z);
                  if (!at) return null;
                  const key = `npc:${npc.npc_id}`;
                  return (
                    <button
                      key={key}
                      type="button"
                      data-marker={key}
                      className={`map-marker npc${selectedKey === key ? " selected" : ""}`}
                      style={at}
                      title={`${npc.name} — ${npc.knowledge.length} знань`}
                      aria-label={`${npc.name}, ${npc.knowledge.length} знань`}
                      onClick={() => setSelection({ kind: "npc", npc })}
                    />
                  );
                })}
                <div className="map-zoom">
                  <button type="button" className="outline-button" onClick={() => zoomAt(ZOOM_STEP, size.width / 2, size.height / 2)} aria-label="Наблизити">+</button>
                  <button type="button" className="outline-button" onClick={() => zoomAt(1 / ZOOM_STEP, size.width / 2, size.height / 2)} aria-label="Віддалити">−</button>
                  <button type="button" className="outline-button" onClick={() => setView(null)}>Уся карта</button>
                </div>
              </div>

              <aside className="panel map-details">
                {!selection ? (
                  <p className="inventory-muted">
                    Натисни на маркер, щоб побачити, що там. Сині точки — NPC, у яких можна взяти знання, яких у тебе ще
                    немає; золоті — вкладені вузли; квадрати — місця для гринду (зелені підходять за AP/DP).
                  </p>
                ) : selection.kind === "spot" ? (
                  <>
                    <div className="eyebrow">{selection.spot.region ?? "ГРИНД"}</div>
                    <h2>{selection.spot.name}</h2>
                    <p className="inventory-muted">
                      Рекомендовано: {selection.spot.sheet_ap ?? "—"} AP / {selection.spot.sheet_dp ?? "—"} DP.
                      {grind.data?.gear.ap != null && ` У тебе: ${grind.data.gear.ap} AP / ${grind.data.gear.dp} DP.`}
                    </p>
                    <p className={`grind-status ${grindStatus.get(selection.spot.spot_id) ?? "unknown"}`}>
                      {GRIND_LABELS[grindStatus.get(selection.spot.spot_id) ?? "unknown"]}
                    </p>
                    <Link className="text-link" href="/grind/">Усі місця для гринду →</Link>
                  </>
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
