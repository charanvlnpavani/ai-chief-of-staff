"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CirclePlay, FileText, Link2, type LucideIcon, Quote } from "lucide-react";

import { api, unwrap } from "@/lib/api";
import type { ItemKind } from "@/lib/library";
import { qk } from "@/lib/queries";

export const libraryKeys = {
  all: qk.library,
  items: [...qk.library, "items"] as const,
  item: (id: string) => [...qk.library, "item", id] as const,
  counts: [...qk.library, "counts"] as const,
  trash: [...qk.library, "trash"] as const,
  tags: [...qk.library, "tags"] as const,
  collections: [...qk.library, "collections"] as const,
};

/** Every library view reads from the same few endpoints, so any change refreshes them all. */
export function useInvalidateLibrary() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: libraryKeys.all });
}

export function useTags() {
  return useQuery({
    queryKey: libraryKeys.tags,
    queryFn: () => unwrap(api.GET("/api/v1/library/tags")),
  });
}

export function useCollections() {
  return useQuery({
    queryKey: libraryKeys.collections,
    queryFn: () => unwrap(api.GET("/api/v1/library/collections")),
  });
}

const KIND_ICON: Record<ItemKind, LucideIcon> = {
  note: FileText,
  link: Link2,
  video: CirclePlay,
  excerpt: Quote,
};

export function KindIcon({ kind, className }: { kind: ItemKind; className?: string }) {
  const Icon = KIND_ICON[kind];
  return <Icon className={className ?? "size-4 text-muted-foreground"} aria-hidden />;
}
