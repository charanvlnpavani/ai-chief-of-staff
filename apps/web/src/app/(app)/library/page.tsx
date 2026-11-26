"use client";

import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { Library, Plus, RotateCcw, Search, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, errorMessage, unwrap } from "@/lib/api";
import {
  type ItemKind,
  type ItemStatus,
  KIND_LABEL,
  type LibraryRow,
  STATUSES,
  duplicateId,
  itemHref,
  parseCapture,
  parseTags,
  savedLabel,
  sharedCapture,
} from "@/lib/library";

import { OrganizeSheet } from "./organize-sheet";
import { KindIcon, libraryKeys, useCollections, useInvalidateLibrary, useTags } from "./shared";

type View = ItemStatus | "all" | "trash";
const ALL = "__all";
const PAGE_SIZE = 30;

// ------------------------------------------------------------------ capture

function CaptureCard({ initial, autoFocus }: { initial: string; autoFocus: boolean }) {
  const router = useRouter();
  const invalidate = useInvalidateLibrary();
  const [text, setText] = useState(initial);
  const [asExcerpt, setAsExcerpt] = useState(false);
  const [source, setSource] = useState("");
  const [tags, setTags] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) box.current?.focus();
  }, [autoFocus]);

  const capture = asExcerpt ? null : parseCapture(text);
  const save = useMutation({
    mutationFn: () => {
      const tagList = parseTags(tags);
      if (asExcerpt) {
        return unwrap(
          api.POST("/api/v1/library/items", {
            body: { kind: "excerpt", excerpt: text.trim(), url: source.trim() || null, tags: tagList },
          }),
        );
      }
      const parsed = parseCapture(text);
      const body =
        parsed?.kind === "link" ? { url: parsed.url, tags: tagList } : { body: text.trim(), tags: tagList };
      return unwrap(api.POST("/api/v1/library/items", { body }));
    },
    onSuccess: (item) => {
      setText("");
      setSource("");
      setTags("");
      setAsExcerpt(false);
      void invalidate();
      toast.success(`Saved “${item.title}”`, {
        action: { label: "Open", onClick: () => router.push(itemHref(item.id)) },
      });
    },
    onError: (error) => {
      const existing = error instanceof ApiError ? duplicateId(error.problem) : null;
      if (existing) {
        toast.info("You already saved this link.", {
          action: { label: "Open it", onClick: () => router.push(itemHref(existing)) },
        });
        return;
      }
      toast.error(errorMessage(error));
    },
  });

  const ready = text.trim().length > 0 && !save.isPending;
  const hint = asExcerpt
    ? "Saved as a quote, kept apart from your notes."
    : capture?.kind === "link"
      ? "Will be saved as a link; the page title is fetched for you."
      : "Will be saved as a note. Paste a web address to save a link.";

  return (
    <Card className="mb-4">
      <CardContent>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (ready) save.mutate();
          }}
        >
          <Label htmlFor="capture" className="sr-only">
            Paste a link or write a note
          </Label>
          <Textarea
            id="capture"
            ref={box}
            rows={2}
            maxLength={asExcerpt ? 10_000 : 100_000}
            placeholder={asExcerpt ? "Paste the passage you want to keep…" : "Paste a link or write a note…"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && ready) {
                e.preventDefault();
                save.mutate();
              }
            }}
          />
          {asExcerpt ? (
            <div className="space-y-1.5">
              <Label htmlFor="capture-source">Source link (optional)</Label>
              <Input
                id="capture-source"
                inputMode="url"
                placeholder="https://…"
                value={source}
                maxLength={2048}
                onChange={(e) => setSource(e.target.value)}
              />
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Input
              aria-label="Tags, separated by commas"
              placeholder="Tags, comma separated"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="min-w-40 flex-1"
            />
            <div className="flex items-center gap-2">
              <Switch id="as-excerpt" checked={asExcerpt} onCheckedChange={setAsExcerpt} />
              <Label htmlFor="as-excerpt" className="text-sm font-normal">
                Save as excerpt
              </Label>
            </div>
            <Button type="submit" disabled={!ready}>
              <Plus className="size-4" aria-hidden /> {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {text.trim() ? hint : "Tip: press ⌘/Ctrl + Enter to save."}
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ rows

function ItemRow({ item, inTrash }: { item: LibraryRow; inTrash: boolean }) {
  const invalidate = useInvalidateLibrary();
  const [confirmPurge, setConfirmPurge] = useState(false);
  const path = { item_id: item.id };

  const favorite = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/library/items/{item_id}", {
          params: { path },
          body: { version: item.version, isFavorite: !item.isFavorite },
        }),
      ),
    onSuccess: () => void invalidate(),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const restore = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/library/items/{item_id}/restore", { params: { path } })),
    onSuccess: () => {
      void invalidate();
      toast.success("Restored");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const trash = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/library/items/{item_id}", { params: { path } })),
    onSuccess: () => {
      void invalidate();
      toast.success("Moved to the trash", { action: { label: "Undo", onClick: () => restore.mutate() } });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const purge = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/library/items/{item_id}/permanent", { params: { path } })),
    onSuccess: () => {
      setConfirmPurge(false);
      void invalidate();
      toast.success("Deleted for good");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const title = inTrash ? (
    <span className="truncate text-sm font-medium">{item.title}</span>
  ) : (
    <Link href={itemHref(item.id)} className="truncate text-sm font-medium hover:underline">
      {item.title}
    </Link>
  );

  return (
    <li className="flex items-start gap-3 px-3 py-2.5">
      <span className="mt-0.5" title={KIND_LABEL[item.kind]}>
        <KindIcon kind={item.kind} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">{title}</div>
        {item.preview ? <p className="line-clamp-2 text-xs text-muted-foreground">{item.preview}</p> : null}
        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {item.siteName ? <span>{item.siteName}</span> : null}
          <span>{savedLabel(item.createdAt)}</span>
          {item.tags.map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
        </div>
      </div>
      {inTrash ? (
        <>
          <Button variant="ghost" size="sm" onClick={() => restore.mutate()} disabled={restore.isPending}>
            <RotateCcw className="size-4" aria-hidden /> Restore
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Delete ${item.title} for good`}
            onClick={() => setConfirmPurge(true)}
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </>
      ) : (
        <>
          <Button
            variant="ghost"
            size="icon"
            aria-label={item.isFavorite ? `Unfavourite ${item.title}` : `Favourite ${item.title}`}
            aria-pressed={item.isFavorite}
            onClick={() => favorite.mutate()}
            disabled={favorite.isPending}
          >
            <Star className={`size-4 ${item.isFavorite ? "fill-current text-amber-500" : ""}`} aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Move ${item.title} to the trash`}
            onClick={() => trash.mutate()}
            disabled={trash.isPending}
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </>
      )}
      {confirmPurge ? (
        <Dialog open onOpenChange={(open) => !open && setConfirmPurge(false)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete for good?</DialogTitle>
              <DialogDescription>
                “{item.title}” will be removed permanently. This cannot be undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmPurge(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={() => purge.mutate()} disabled={purge.isPending}>
                Delete for good
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </li>
  );
}

// ------------------------------------------------------------------ page

function useSearchInUrl(): [string, (value: string) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const fromUrl = params.get("q") ?? "";
  const [value, setValue] = useState(fromUrl);

  // Debounced, so typing does not add a history entry per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (value === fromUrl) return;
      const next = new URLSearchParams(params.toString());
      if (value.trim()) next.set("q", value);
      else next.delete("q");
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    }, 250);
    return () => clearTimeout(timer);
  }, [value, fromUrl, params, pathname, router]);

  return [value, setValue];
}

function LibraryContent() {
  const params = useSearchParams();
  const router = useRouter();
  const [search, setSearch] = useSearchInUrl();
  const [view, setView] = useState<View>("inbox");
  const [kind, setKind] = useState<ItemKind | typeof ALL>(ALL);
  const [tag, setTag] = useState<string>(ALL);
  const [collection, setCollection] = useState<string>(ALL);
  const [favorites, setFavorites] = useState(false);
  const tags = useTags();
  const collections = useCollections();

  // A phone's share sheet opens /library?url=…&text=…&title=… (see manifest.webmanifest).
  const [initialCapture] = useState(() =>
    sharedCapture({ title: params.get("title"), text: params.get("text"), url: params.get("url") }),
  );
  const focusCapture = params.has("capture") || Boolean(initialCapture);
  useEffect(() => {
    if (params.has("url") || params.has("text") || params.has("title") || params.has("capture")) {
      router.replace("/library", { scroll: false }); // keep shared text out of history and reloads
    }
  }, [params, router]);

  const q = params.get("q") ?? "";
  const counts = useQuery({
    queryKey: libraryKeys.counts,
    queryFn: () => unwrap(api.GET("/api/v1/library/counts")),
  });
  const inTrash = view === "trash";
  const filters = {
    q: q.trim() || undefined,
    status: view === "all" || inTrash ? undefined : view,
    kind: kind === ALL ? undefined : kind,
    tag: tag === ALL ? undefined : tag,
    collection: collection === ALL ? undefined : collection,
    favorite: favorites ? true : undefined,
  };
  const items = useInfiniteQuery({
    queryKey: inTrash ? libraryKeys.trash : [...libraryKeys.items, filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      inTrash
        ? unwrap(api.GET("/api/v1/library/trash", { params: { query: { limit: PAGE_SIZE, cursor: pageParam } } }))
        : unwrap(
            api.GET("/api/v1/library/items", {
              params: { query: { ...filters, limit: PAGE_SIZE, cursor: pageParam } },
            }),
          ),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });

  const rows = items.data?.pages.flatMap((p) => p.items) ?? [];
  const filtered = Boolean(filters.q || filters.kind || filters.tag || filters.collection || favorites);
  const count = (key: keyof NonNullable<typeof counts.data>) => counts.data?.[key];
  const tabs: { value: View; label: string; n?: number }[] = [
    ...STATUSES.map((s) => ({ value: s.value as View, label: s.label, n: count(s.value === "to_read" ? "toRead" : s.value) })),
    { value: "all", label: "All" },
    { value: "trash", label: "Trash", n: count("trash") },
  ];

  return (
    <>
      <PageHeader
        title="Library"
        description="Save links, videos, quotes and notes once; find them again when you need them."
        actions={<OrganizeSheet />}
      />
      <CaptureCard key={initialCapture} initial={initialCapture} autoFocus={focusCapture} />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Tabs value={view} onValueChange={(v) => setView(v as View)} className="max-w-full overflow-x-auto">
          <TabsList>
            {tabs.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
                {t.n ? <span className="ml-1 tabular text-xs text-muted-foreground">{t.n}</span> : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {!inTrash ? (
          <div className="relative w-full sm:ml-auto sm:w-auto">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input
              type="search"
              aria-label="Search the library"
              placeholder="Search"
              value={search}
              maxLength={200}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-8 sm:w-56"
            />
          </div>
        ) : null}
      </div>

      {!inTrash ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Select value={kind} onValueChange={(v) => setKind(v as ItemKind | typeof ALL)}>
            <SelectTrigger className="w-32" aria-label="Kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All kinds</SelectItem>
              {(Object.keys(KIND_LABEL) as ItemKind[]).map((k) => (
                <SelectItem key={k} value={k}>
                  {KIND_LABEL[k]}s
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={tag} onValueChange={setTag}>
            <SelectTrigger className="w-36" aria-label="Tag">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All tags</SelectItem>
              {(tags.data ?? []).map((t) => (
                <SelectItem key={t.id} value={t.name}>
                  {t.name} ({t.itemCount})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={collection} onValueChange={setCollection}>
            <SelectTrigger className="w-40" aria-label="Collection">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All collections</SelectItem>
              {(collections.data ?? []).map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name} ({c.itemCount})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant={favorites ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={favorites}
            onClick={() => setFavorites((f) => !f)}
          >
            <Star className={`size-4 ${favorites ? "fill-current text-amber-500" : ""}`} aria-hidden /> Favourites
          </Button>
        </div>
      ) : null}

      {items.isPending ? (
        <LoadingRows rows={5} />
      ) : items.isError ? (
        <ErrorState error={items.error} onRetry={() => items.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={inTrash ? Trash2 : Library}
          title={inTrash ? "The trash is empty" : filtered ? "Nothing matches" : "Nothing here yet"}
          description={
            inTrash
              ? "Items you delete wait here until you restore them or delete them for good."
              : filtered
                ? "Try fewer words or clear a filter."
                : "Paste a link or write a note above to save it."
          }
        />
      ) : (
        <>
          <ul className="divide-y rounded-lg border">
            {rows.map((item) => (
              <ItemRow key={item.id} item={item} inTrash={inTrash} />
            ))}
          </ul>
          {items.hasNextPage ? (
            <div className="mt-3 flex justify-center">
              <Button variant="outline" onClick={() => items.fetchNextPage()} disabled={items.isFetchingNextPage}>
                {items.isFetchingNextPage ? "Loading…" : "Load more"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}

export default function LibraryPage() {
  return (
    <Suspense fallback={<LoadingRows rows={5} />}>
      <LibraryContent />
    </Suspense>
  );
}
