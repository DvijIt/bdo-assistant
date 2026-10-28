"use client";

import Image from "next/image";
import { ReactNode, useEffect, useState } from "react";

import { API, fetchJson } from "../_lib/api";

type Images = { items: boolean; knowledge: boolean };

// Чи є картинки в папці імпорту, питаємо один раз на сторінку: без них кожна іконка дала б 404.
let available: Promise<Images> | null = null;

function imagesAvailable() {
  available ??= fetchJson<{ images?: Images } | null>("/api/game-data")
    .then((status) => status?.images ?? { items: false, knowledge: false })
    .catch(() => ({ items: false, knowledge: false }));
  return available;
}

/** Картинка з власного клієнта гри (extractor `icons` / `knowledge-icons`); без неї — `fallback`. */
export function GameImage({
  kind,
  id,
  size,
  className,
  fallback = null,
}: {
  kind: "item" | "knowledge";
  id: number;
  size: number;
  className?: string;
  fallback?: ReactNode;
}) {
  const [enabled, setEnabled] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void imagesAvailable().then((images) => {
      if (!cancelled) setEnabled(kind === "item" ? images.items : images.knowledge);
    });
    return () => {
      cancelled = true;
    };
  }, [kind]);

  if (!enabled || failed) return <>{fallback}</>;
  return (
    <Image
      unoptimized
      className={className}
      src={`${API}/api/game-data/icons/${kind}/${id}`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}
