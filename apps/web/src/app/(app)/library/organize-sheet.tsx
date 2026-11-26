"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, FolderOpen, Pencil, Plus, Tag, Trash2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { LoadingRows } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";

import { useCollections, useInvalidateLibrary, useTags } from "./shared";

type Collection = Schemas["CollectionOut"];
type TagRow = Schemas["TagOut"];

/** A name shown as text, or as an input while editing. */
function EditableName({
  name,
  label,
  maxLength,
  onSave,
  onDelete,
  count,
}: {
  name: string;
  label: string;
  maxLength: number;
  onSave: (name: string) => void;
  onDelete: () => void;
  count: number;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);

  if (editing) {
    return (
      <form
        className="flex items-center gap-1"
        onSubmit={(event) => {
          event.preventDefault();
          if (value.trim() && value.trim() !== name) onSave(value.trim());
          setEditing(false);
        }}
      >
        <Input
          aria-label={`New name for ${label} ${name}`}
          value={value}
          maxLength={maxLength}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          className="h-8"
        />
        <Button type="submit" size="icon" variant="ghost" aria-label="Save name">
          <Check className="size-4" aria-hidden />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label="Cancel"
          onClick={() => {
            setValue(name);
            setEditing(false);
          }}
        >
          <X className="size-4" aria-hidden />
        </Button>
      </form>
    );
  }
  return (
    <div className="flex items-center gap-1">
      <span className="min-w-0 flex-1 truncate text-sm">{name}</span>
      <span className="tabular text-xs text-muted-foreground">{count}</span>
      <Button size="icon" variant="ghost" aria-label={`Rename ${label} ${name}`} onClick={() => setEditing(true)}>
        <Pencil className="size-4" aria-hidden />
      </Button>
      <Button size="icon" variant="ghost" aria-label={`Delete ${label} ${name}`} onClick={onDelete}>
        <Trash2 className="size-4" aria-hidden />
      </Button>
    </div>
  );
}

function Collections() {
  const collections = useCollections();
  const invalidate = useInvalidateLibrary();
  const [name, setName] = useState("");
  const done = (message: string) => () => {
    void invalidate();
    toast.success(message);
  };
  const onError = (error: unknown) => toast.error(errorMessage(error));

  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/library/collections", { body: { name: name.trim() } })),
    onSuccess: () => {
      setName("");
      void invalidate();
    },
    onError,
  });
  const rename = useMutation({
    mutationFn: ({ c, next }: { c: Collection; next: string }) =>
      unwrap(
        api.PATCH("/api/v1/library/collections/{collection_id}", {
          params: { path: { collection_id: c.id } },
          body: { version: c.version, name: next },
        }),
      ),
    onSuccess: done("Collection renamed"),
    onError,
  });
  const remove = useMutation({
    mutationFn: (c: Collection) =>
      unwrap(
        api.DELETE("/api/v1/library/collections/{collection_id}", { params: { path: { collection_id: c.id } } }),
      ),
    onSuccess: done("Collection deleted; its items stay in the library"),
    onError,
  });

  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <FolderOpen className="size-4" aria-hidden /> Collections
      </h3>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <Label htmlFor="new-collection" className="sr-only">
          New collection
        </Label>
        <Input
          id="new-collection"
          placeholder="New collection"
          value={name}
          maxLength={60}
          onChange={(e) => setName(e.target.value)}
          className="h-8"
        />
        <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>
          <Plus className="size-4" aria-hidden /> Add
        </Button>
      </form>
      {collections.isPending ? (
        <LoadingRows rows={2} />
      ) : (collections.data ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground">No collections yet. An item can live in one collection.</p>
      ) : (
        <ul className="space-y-1">
          {collections.data?.map((c) => (
            <li key={c.id}>
              <EditableName
                name={c.name}
                label="collection"
                maxLength={60}
                count={c.itemCount}
                onSave={(next) => rename.mutate({ c, next })}
                onDelete={() => remove.mutate(c)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Tags() {
  const tags = useTags();
  const invalidate = useInvalidateLibrary();
  const onError = (error: unknown) => toast.error(errorMessage(error));

  const rename = useMutation({
    mutationFn: ({ t, next }: { t: TagRow; next: string }) =>
      unwrap(api.PATCH("/api/v1/library/tags/{tag_id}", { params: { path: { tag_id: t.id } }, body: { name: next } })),
    onSuccess: (result, { t }) => {
      void invalidate();
      toast.success(result.id === t.id ? "Tag renamed" : `Merged into “${result.name}”`);
    },
    onError,
  });
  const remove = useMutation({
    mutationFn: (t: TagRow) => unwrap(api.DELETE("/api/v1/library/tags/{tag_id}", { params: { path: { tag_id: t.id } } })),
    onSuccess: () => {
      void invalidate();
      toast.success("Tag removed from every item");
    },
    onError,
  });

  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <Tag className="size-4" aria-hidden /> Tags
      </h3>
      <p className="text-xs text-muted-foreground">Renaming a tag to an existing tag&apos;s name merges them.</p>
      {tags.isPending ? (
        <LoadingRows rows={2} />
      ) : (tags.data ?? []).length === 0 ? (
        <p className="text-xs text-muted-foreground">No tags yet. Add them when you save something.</p>
      ) : (
        <ul className="space-y-1">
          {tags.data?.map((t) => (
            <li key={t.id}>
              <EditableName
                name={t.name}
                label="tag"
                maxLength={40}
                count={t.itemCount}
                onSave={(next) => rename.mutate({ t, next })}
                onDelete={() => remove.mutate(t)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function OrganizeSheet() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">
          <FolderOpen className="size-4" aria-hidden /> Organize
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Organize</SheetTitle>
          <SheetDescription>Collections and tags for your library.</SheetDescription>
        </SheetHeader>
        <div className="space-y-6 px-4 pb-6">
          <Collections />
          <Separator />
          <Tags />
        </div>
      </SheetContent>
    </Sheet>
  );
}
