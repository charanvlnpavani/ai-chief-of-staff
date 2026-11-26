import type { Schemas } from "@/lib/api";

export type LibraryItem = Schemas["ItemOut"];
export type LibraryRow = Schemas["ItemSummaryOut"];
export type ItemStatus = LibraryRow["status"];
export type ItemKind = LibraryRow["kind"];

export const STATUSES: { value: ItemStatus; label: string }[] = [
  { value: "inbox", label: "Inbox" },
  { value: "to_read", label: "To read" },
  { value: "reading", label: "Reading" },
  { value: "archived", label: "Archived" },
];

export const KIND_LABEL: Record<ItemKind, string> = {
  note: "Note",
  link: "Link",
  video: "Video",
  excerpt: "Excerpt",
};

// "https://…" with no spaces, or a bare host ending in a letter-only top-level domain
// ("example.com/post", "bücher.de"), so "3.14" and "e.g." stay notes.
const HAS_SCHEME = /^https?:\/\/\S+$/i;
const BARE_HOST = /^([\p{L}\p{N}-]+\.)+\p{L}{2,}(:\d+)?([/?#]\S*)?$/u;

export type Capture = { kind: "link"; url: string } | { kind: "note"; body: string } | null;

/**
 * What the one capture box means: a lone web address is a link (or video; the server
 * decides), anything else is a note. Blank input is nothing.
 */
export function parseCapture(input: string): Capture {
  const text = input.trim();
  if (!text) return null;
  if (HAS_SCHEME.test(text) || BARE_HOST.test(text)) {
    return { kind: "link", url: text };
  }
  return { kind: "note", body: text };
}

/**
 * Builds the capture text from a phone's share sheet (?title=&text=&url=). Many apps put
 * the link inside `text`, so a URL found there is used when `url` is missing.
 */
export function sharedCapture(params: { title?: string | null; text?: string | null; url?: string | null }): string {
  const url = params.url?.trim();
  if (url) return url;
  const text = params.text?.trim() ?? "";
  const found = text.match(/https?:\/\/\S+/i)?.[0];
  if (found) return found;
  return [params.title?.trim(), text].filter(Boolean).join("\n");
}

/** "Python, rust ,, #Go" -> ["Python", "rust", "Go"] (case-insensitive repeats dropped). */
export function parseTags(input: string): string[] {
  const seen = new Map<string, string>();
  for (const raw of input.split(",")) {
    const tag = raw.trim().replace(/^#+/, "").trim();
    if (tag && !seen.has(tag.toLowerCase())) seen.set(tag.toLowerCase(), tag);
  }
  return [...seen.values()];
}

/** The API's 409 for a link saved before carries the existing item's id. */
export function duplicateId(problem: unknown): string | null {
  if (typeof problem !== "object" || problem === null) return null;
  const record = problem as Record<string, unknown>;
  return record.code === "library_duplicate" && typeof record.existingId === "string" ? record.existingId : null;
}

export function savedLabel(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) });
}

/** The item page keeps the id in the query string, like the app's other detail views. */
export function itemHref(id: string): string {
  return `/library/item?id=${encodeURIComponent(id)}`;
}
