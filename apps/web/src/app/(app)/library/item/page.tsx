"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RefreshCw, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { ErrorState, LoadingRows } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { type ItemStatus, KIND_LABEL, type LibraryItem, STATUSES, itemHref, parseTags, savedLabel } from "@/lib/library";

import { KindIcon, libraryKeys, useCollections, useInvalidateLibrary } from "../shared";

const NO_COLLECTION = "__none";

function ItemEditor({ item }: { item: LibraryItem }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const invalidate = useInvalidateLibrary();
  const collections = useCollections();
  const [title, setTitle] = useState(item.title);
  const [body, setBody] = useState(item.body ?? "");
  const [excerpt, setExcerpt] = useState(item.excerpt ?? "");
  const [tags, setTags] = useState(item.tags.join(", "));
  const path = { item_id: item.id };

  const applied = (updated: LibraryItem) => {
    queryClient.setQueryData(libraryKeys.item(item.id), updated);
    void invalidate();
  };
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.code === "version_conflict") {
      toast.error("This item changed in another tab. Reloaded the latest version.");
      void queryClient.invalidateQueries({ queryKey: libraryKeys.item(item.id) });
      return;
    }
    toast.error(errorMessage(error));
  };

  const patch = useMutation({
    mutationFn: (body: Omit<Schemas["ItemUpdate"], "version">) =>
      unwrap(api.PATCH("/api/v1/library/items/{item_id}", { params: { path }, body: { ...body, version: item.version } })),
    onSuccess: applied,
    onError,
  });
  const refresh = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/library/items/{item_id}/refresh", { params: { path } })),
    onSuccess: (updated) => {
      applied(updated);
      setTitle(updated.title);
      toast[updated.metadataStatus === "fetched" ? "success" : "info"](
        updated.metadataStatus === "fetched" ? "Details updated" : "Couldn't reach the page; kept what was there",
      );
    },
    onError,
  });
  const restore = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/library/items/{item_id}/restore", { params: { path } })),
    onSuccess: (restored) => {
      applied(restored);
      router.push(itemHref(item.id));
    },
    onError,
  });
  const trash = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/library/items/{item_id}", { params: { path } })),
    onSuccess: () => {
      void invalidate();
      toast.success("Moved to the trash", { action: { label: "Undo", onClick: () => restore.mutate() } });
      router.push("/library");
    },
    onError,
  });

  const textChanged =
    title.trim() !== item.title ||
    body !== (item.body ?? "") ||
    excerpt !== (item.excerpt ?? "") ||
    parseTags(tags).join(",") !== item.tags.join(",");

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <Button asChild variant="ghost" size="sm">
          <Link href="/library">
            <ArrowLeft className="size-4" aria-hidden /> Library
          </Link>
        </Button>
        <div className="ml-auto flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label={item.isFavorite ? "Unfavourite" : "Favourite"}
            aria-pressed={item.isFavorite}
            onClick={() => patch.mutate({ isFavorite: !item.isFavorite })}
          >
            <Star className={`size-4 ${item.isFavorite ? "fill-current text-amber-500" : ""}`} aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Move to the trash" onClick={() => trash.mutate()}>
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      </div>

      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          patch.mutate(
            {
              title: title.trim() || undefined,
              body: body.trim() ? body : null,
              ...(item.kind === "excerpt" || item.excerpt ? { excerpt: excerpt.trim() ? excerpt : null } : {}),
              tags: parseTags(tags),
            },
            {
              onSuccess: (updated) => {
                // Take back the server's cleaned text (trimmed, deduplicated tags), so the
                // form matches what was saved and "Save changes" disables again.
                setTitle(updated.title);
                setBody(updated.body ?? "");
                setExcerpt(updated.excerpt ?? "");
                setTags(updated.tags.join(", "));
                toast.success("Saved");
              },
            },
          );
        }}
      >
        <div className="flex items-start gap-3">
          <span className="mt-2" title={KIND_LABEL[item.kind]}>
            <KindIcon kind={item.kind} className="size-5 text-muted-foreground" />
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            <Label htmlFor="item-title" className="sr-only">
              Title
            </Label>
            <Input
              id="item-title"
              value={title}
              maxLength={300}
              onChange={(e) => setTitle(e.target.value)}
              className="text-lg font-semibold"
            />
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">{KIND_LABEL[item.kind]}</Badge>
              <span>Saved {savedLabel(item.createdAt)}</span>
              {item.author ? <span>by {item.author}</span> : null}
            </div>
          </div>
        </div>

        {item.url ? (
          <Card>
            <CardContent className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted-foreground">Source{item.siteName ? ` · ${item.siteName}` : ""}</p>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                  className="inline-flex max-w-full items-center gap-1 truncate text-sm text-primary hover:underline"
                >
                  <span className="truncate">{item.url}</span>
                  <ExternalLink className="size-3.5 shrink-0" aria-hidden />
                </a>
              </div>
              {item.kind !== "excerpt" ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => refresh.mutate()}
                  disabled={refresh.isPending}
                >
                  <RefreshCw className={`size-4 ${refresh.isPending ? "animate-spin" : ""}`} aria-hidden /> Refresh
                  details
                </Button>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Status</Label>
            <Select value={item.status} onValueChange={(v) => patch.mutate({ status: v as ItemStatus })}>
              <SelectTrigger className="w-full" aria-label="Status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUSES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Collection</Label>
            <Select
              value={item.collectionId ?? NO_COLLECTION}
              onValueChange={(v) => patch.mutate({ collectionId: v === NO_COLLECTION ? null : v })}
            >
              <SelectTrigger className="w-full" aria-label="Collection">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_COLLECTION}>No collection</SelectItem>
                {(collections.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="item-tags">Tags</Label>
          <Input
            id="item-tags"
            placeholder="Comma separated"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>

        {item.kind === "excerpt" || item.excerpt ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Saved excerpt</CardTitle>
              <p className="text-xs text-muted-foreground">Text from the source, kept apart from your note.</p>
            </CardHeader>
            <CardContent>
              <Label htmlFor="item-excerpt" className="sr-only">
                Saved excerpt
              </Label>
              <Textarea
                id="item-excerpt"
                rows={5}
                maxLength={10_000}
                value={excerpt}
                onChange={(e) => setExcerpt(e.target.value)}
                className="border-l-4 border-l-primary/40 italic"
              />
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">My note</CardTitle>
            <p className="text-xs text-muted-foreground">Your own words. Line breaks are kept.</p>
          </CardHeader>
          <CardContent>
            <Label htmlFor="item-body" className="sr-only">
              My note
            </Label>
            <Textarea
              id="item-body"
              rows={8}
              maxLength={100_000}
              placeholder="Why you saved this, what to do with it…"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button type="submit" disabled={!textChanged || patch.isPending}>
            {patch.isPending ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </form>
    </>
  );
}

function NotInLibrary() {
  return (
    <div className="space-y-3">
      <p className="text-sm">This item isn&apos;t in your library. It may be in the trash.</p>
      <Button asChild variant="outline" size="sm">
        <Link href="/library">Back to the library</Link>
      </Button>
    </div>
  );
}

function ItemContent() {
  const id = useSearchParams().get("id") ?? "";
  const item = useQuery({
    enabled: Boolean(id),
    queryKey: libraryKeys.item(id),
    queryFn: () => unwrap(api.GET("/api/v1/library/items/{item_id}", { params: { path: { item_id: id } } })),
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
  });

  if (!id) return <NotInLibrary />;
  if (item.isPending) return <LoadingRows rows={6} />;
  if (item.isError) {
    // A malformed id is a 422; either way there is nothing of the user's to show.
    if (item.error instanceof ApiError && [404, 422].includes(item.error.status)) return <NotInLibrary />;
    return <ErrorState error={item.error} onRetry={() => item.refetch()} />;
  }
  // Keyed by id only, so a status or favourite change never wipes unsaved text. Saves always
  // send the latest version from the server copy.
  return <ItemEditor key={item.data.id} item={item.data} />;
}

export default function LibraryItemPage() {
  return (
    <Suspense fallback={<LoadingRows rows={6} />}>
      <ItemContent />
    </Suspense>
  );
}
