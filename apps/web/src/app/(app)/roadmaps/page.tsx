"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Circle, Flame, Pause, Play, Plus, Route, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Private, usePrivacy } from "@/components/privacy";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { api, ApiError, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { dayLabel, formatMinutes, percent } from "@/lib/format";
import { qk } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Roadmap = Schemas["RoadmapOut"];
type Detail = Schemas["RoadmapDetailOut"];
type Draft = Schemas["RoadmapDraft"];
type Task = Schemas["RoadmapTaskOut"];
type Level = Task["level"];

const LEVELS: { key: Level; label: string }[] = [
  { key: "basic", label: "Basic" },
  { key: "intermediate", label: "Intermediate" },
  { key: "advanced", label: "Advanced" },
  { key: "pro", label: "Pro" },
];
const levelLabel = (level: Level | null | undefined) => LEVELS.find((l) => l.key === level)?.label ?? "—";

function detailKey(id: string, ahead: boolean) {
  return [...qk.roadmaps, "detail", id, { ahead }] as const;
}

// ------------------------------------------------------------------ new roadmap

function DraftPreview({ draft }: { draft: Draft }) {
  const minutes = draft.days.reduce((sum, d) => sum + d.tasks.reduce((s, t) => s + (t.minutes ?? 0), 0), 0);
  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium">{draft.title}</p>
        <Badge variant="secondary">{draft.source === "template" ? "Built-in" : "Drafted by Claude"}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        {draft.days.length} days · about {formatMinutes(minutes / draft.days.length)} a day
      </p>
      <ul className="grid grid-cols-2 gap-2 text-sm">
        {LEVELS.map((l) => (
          <li key={l.key} className="rounded-md bg-muted/50 p-2">
            <span className="block font-medium">{l.label}</span>
            <span className="text-muted-foreground">{draft.days.filter((d) => d.level === l.key).length} days</span>
          </li>
        ))}
      </ul>
      <ol className="space-y-1 text-sm">
        {draft.days.slice(0, 3).map((d, i) => (
          <li key={i}>
            <span className="text-muted-foreground">Day {i + 1}: </span>
            {d.tasks.map((t) => t.title).join(" · ")}
          </li>
        ))}
        {draft.days.length > 3 ? <li className="text-muted-foreground">…and {draft.days.length - 3} more days</li> : null}
      </ol>
    </div>
  );
}

function NewRoadmapDialog({ onCreated }: { onCreated: (id: string) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState("");
  const [days, setDays] = useState("45");
  const [minutes, setMinutes] = useState("60");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [aiMissing, setAiMissing] = useState(false);
  const templates = useQuery({
    queryKey: [...qk.roadmaps, "templates"],
    queryFn: () => unwrap(api.GET("/api/v1/roadmaps/templates")),
    enabled: open,
  });

  const build = useMutation({
    mutationFn: (topic: string) =>
      unwrap(
        api.POST("/api/v1/roadmaps/draft", {
          body: { subject: topic, targetDays: Number(days), minutesPerDay: Number(minutes) },
        }),
      ),
    onMutate: () => {
      setDraft(null);
      setAiMissing(false);
    },
    onSuccess: setDraft,
    onError: (error) => {
      if (error instanceof ApiError && error.code === "ai_not_configured") setAiMissing(true);
      else toast.error(errorMessage(error));
    },
  });
  const save = useMutation({
    mutationFn: (body: Draft) => unwrap(api.POST("/api/v1/roadmaps", { body })),
    onSuccess: (detail) => {
      queryClient.setQueryData(detailKey(detail.id, false), detail);
      void queryClient.invalidateQueries({ queryKey: [...qk.roadmaps, "list"] });
      toast.success("Roadmap saved. Day 1 is ready.");
      onCreated(detail.id);
      setOpen(false);
      setSubject("");
      setDraft(null);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setDraft(null);
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" aria-hidden /> New roadmap
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New roadmap</DialogTitle>
          <DialogDescription>Type a subject. You get daily tasks from basics to pro level and preview them before saving.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (subject.trim()) build.mutate(subject.trim());
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="roadmap-subject">Subject</Label>
            <Input
              id="roadmap-subject"
              required
              maxLength={80}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="e.g. DSA, System design, React"
            />
          </div>
          {templates.data && templates.data.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Built-in (free, no AI):</span>
              {templates.data.map((t) => (
                <Button
                  key={t.key}
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setSubject(t.subject);
                    build.mutate(t.subject);
                  }}
                >
                  {t.subject} · {t.days} days
                </Button>
              ))}
            </div>
          ) : null}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="roadmap-days">About how many days</Label>
              <Input id="roadmap-days" type="number" min={7} max={180} value={days} onChange={(e) => setDays(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="roadmap-minutes">Minutes per day</Label>
              <Input id="roadmap-minutes" type="number" min={15} max={300} step={5} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Days and minutes shape roadmaps that Claude drafts. Built-in roadmaps have a fixed plan.
          </p>
          <Button type="submit" variant="outline" className="w-full" disabled={!subject.trim() || build.isPending}>
            <Sparkles className="size-4" aria-hidden /> {build.isPending ? "Building roadmap…" : "Build roadmap"}
          </Button>
        </form>
        {aiMissing ? (
          <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            Roadmaps for new subjects are drafted by Claude, which needs <code>ANTHROPIC_API_KEY</code> in{" "}
            <code>backend/.env</code>. Built-in roadmaps above work without it.
          </p>
        ) : null}
        {draft ? (
          <>
            <DraftPreview draft={draft} />
            <DialogFooter>
              <Button onClick={() => save.mutate(draft)} disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save roadmap and start day 1"}
              </Button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// ------------------------------------------------------------------ list

function RoadmapCard({ roadmap, selected, onSelect }: { roadmap: Roadmap; selected: boolean; onSelect: () => void }) {
  const { hidden } = usePrivacy();
  const p = roadmap.progress;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-xl border bg-card p-4 text-left transition-colors hover:bg-muted/40",
        selected && "border-primary ring-1 ring-primary",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{roadmap.title}</p>
          <p className="text-xs text-muted-foreground">
            {roadmap.status === "completed"
              ? "Completed"
              : roadmap.status === "paused"
                ? "Paused"
                : `Day ${p.currentDay ?? p.totalDays} of ${p.totalDays} · ${levelLabel(p.currentLevel)}`}
          </p>
        </div>
        <span className="tabular text-lg font-semibold">
          <Private>{percent(p.percent)}</Private>
        </span>
      </div>
      <Progress className="mt-3" value={hidden ? 0 : Math.round(p.percent * 100)} aria-label={`${roadmap.title} progress`} />
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {p.streakDays > 0 ? (
          <span className="flex items-center gap-0.5 text-amber-600 dark:text-amber-400">
            <Flame className="size-3.5" aria-hidden /> <Private>{p.streakDays}</Private>-day streak
          </span>
        ) : null}
        {p.projectedFinish ? <span>Finish {dayLabel(p.projectedFinish)}</span> : null}
      </div>
    </button>
  );
}

// ------------------------------------------------------------------ detail

function TaskRow({ task, onToggle, disabled }: { task: Task; onToggle?: (done: boolean) => void; disabled?: boolean }) {
  const done = Boolean(task.completedOn);
  return (
    <li className="flex items-start gap-3 py-2">
      {onToggle ? (
        <Checkbox
          className="mt-0.5"
          checked={done}
          disabled={disabled}
          aria-label={`${done ? "Undo" : "Complete"} ${task.title}`}
          onCheckedChange={() => onToggle(!done)}
        />
      ) : done ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-label="Done" />
      ) : (
        <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground/50" aria-label="Not done" />
      )}
      <div className="min-w-0 flex-1">
        <p className={cn("text-sm", done && "text-muted-foreground line-through")}>{task.title}</p>
        {task.detail ? <p className="text-xs text-muted-foreground">{task.detail}</p> : null}
      </div>
      <span className="shrink-0 text-xs text-muted-foreground">{formatMinutes(task.minutes)}</span>
    </li>
  );
}

function FullRoadmap({ detail }: { detail: Detail }) {
  const [openLevel, setOpenLevel] = useState<Level | null>(detail.progress.currentLevel ?? null);
  const byDay = new Map<number, Task[]>();
  for (const t of detail.tasks) byDay.set(t.day, [...(byDay.get(t.day) ?? []), t]);
  return (
    <div className="space-y-2">
      {LEVELS.map((l) => {
        const counts = detail.progress.levels.find((x) => x.level === l.key);
        if (!counts) return null;
        const open = openLevel === l.key;
        const days = [...byDay.entries()].filter(([, tasks]) => tasks[0].level === l.key);
        return (
          <section key={l.key} className="rounded-lg border">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
              aria-expanded={open}
              onClick={() => setOpenLevel(open ? null : l.key)}
            >
              <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
              <span className="font-medium">{l.label}</span>
              <span className="text-muted-foreground">
                · days {days[0]?.[0]}–{days[days.length - 1]?.[0]}
              </span>
              <span className="tabular ml-auto text-muted-foreground">
                <Private>{counts.done}</Private>/{counts.total} tasks
              </span>
            </button>
            {open ? (
              <ol className="space-y-3 border-t px-3 py-2">
                {days.map(([day, tasks]) => (
                  <li key={day}>
                    <p className={cn("text-xs font-medium text-muted-foreground", day === detail.progress.currentDay && "text-primary")}>
                      Day {day}
                      {day === detail.progress.currentDay ? " · today" : ""}
                    </p>
                    <ul className="divide-y">
                      {tasks.map((t) => (
                        <TaskRow key={t.id} task={t} />
                      ))}
                    </ul>
                  </li>
                ))}
              </ol>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function RoadmapDetail({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const [ahead, setAhead] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const detail = useQuery({
    queryKey: detailKey(id, ahead),
    queryFn: () => unwrap(api.GET("/api/v1/roadmaps/{roadmap_id}", { params: { path: { roadmap_id: id }, query: { ahead } } })),
  });
  const store = (next: Detail) => {
    queryClient.setQueryData(detailKey(id, ahead), next);
    void queryClient.invalidateQueries({ queryKey: [...qk.roadmaps, "list"] });
  };
  const toggle = useMutation({
    mutationFn: ({ taskId, done }: { taskId: string; done: boolean }) => {
      const params = { params: { path: { roadmap_id: id, task_id: taskId }, query: { ahead } } };
      return unwrap(
        done
          ? api.PUT("/api/v1/roadmaps/{roadmap_id}/tasks/{task_id}/done", params)
          : api.DELETE("/api/v1/roadmaps/{roadmap_id}/tasks/{task_id}/done", params),
      );
    },
    onSuccess: (next, { done }) => {
      store(next);
      if (done && next.status === "completed") toast.success("Roadmap complete. That's basic to pro, done.");
      else if (done && next.today.complete && !ahead) toast.success("Today's tasks are done.");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const setStatus = useMutation({
    mutationFn: (status: "active" | "paused") =>
      unwrap(
        api.PATCH("/api/v1/roadmaps/{roadmap_id}", {
          params: { path: { roadmap_id: id } },
          body: { status, version: detail.data?.version },
        }),
      ),
    onSuccess: store,
    onError: (error) => {
      toast.error(errorMessage(error));
      void queryClient.invalidateQueries({ queryKey: qk.roadmaps });
    },
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/roadmaps/{roadmap_id}", { params: { path: { roadmap_id: id } } })),
    onSuccess: () => {
      toast.success("Roadmap deleted");
      void queryClient.invalidateQueries({ queryKey: [...qk.roadmaps, "list"] });
      onDeleted();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (detail.isPending) return <LoadingRows rows={4} />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const d = detail.data;
  const today = d.today;
  const nextDay = d.progress.currentDay;

  return (
    <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
      <Card className="self-start">
        <CardHeader>
          <CardTitle>
            {today.finished ? "Roadmap complete" : `Today · Day ${today.days.join(" & ")}`}
          </CardTitle>
          <CardDescription>
            {today.finished
              ? `Finished ${d.progress.done} tasks from basic to pro.`
              : `${levelLabel(today.tasks[0]?.level)} level · ${dayLabel(today.date)}`}
          </CardDescription>
          <CardAction className="flex gap-1">
            {d.status === "active" ? (
              <Button variant="ghost" size="icon" title="Pause" aria-label="Pause roadmap" onClick={() => setStatus.mutate("paused")}>
                <Pause className="size-4" aria-hidden />
              </Button>
            ) : d.status === "paused" ? (
              <Button variant="ghost" size="icon" title="Resume" aria-label="Resume roadmap" onClick={() => setStatus.mutate("active")}>
                <Play className="size-4" aria-hidden />
              </Button>
            ) : null}
            <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
              <DialogTrigger asChild>
                <Button variant="ghost" size="icon" title="Delete" aria-label="Delete roadmap">
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Delete “{d.title}”?</DialogTitle>
                  <DialogDescription>Its days and your ticks disappear from Personal OS.</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setConfirmDelete(false)}>
                    Cancel
                  </Button>
                  <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                    Delete roadmap
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-3">
          {today.tasks.length > 0 ? (
            <ul className="divide-y">
              {today.tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  disabled={toggle.isPending}
                  onToggle={(done) => toggle.mutate({ taskId: t.id, done })}
                />
              ))}
            </ul>
          ) : null}
          {today.complete && !today.finished && nextDay !== null && nextDay !== undefined && !today.days.includes(nextDay) ? (
            <div className="rounded-lg bg-primary/5 p-3 text-sm">
              <p className="font-medium">Today&apos;s tasks are done.</p>
              <p className="text-muted-foreground">Day {nextDay} will be here tomorrow.</p>
              {today.canGoAhead ? (
                <Button className="mt-2" size="sm" variant="outline" onClick={() => setAhead(true)}>
                  Start day {nextDay} now
                </Button>
              ) : null}
            </div>
          ) : null}
          {d.status === "paused" ? (
            <p className="text-xs text-muted-foreground">Paused. You can still tick tasks; resume to show it as active.</p>
          ) : null}
        </CardContent>
      </Card>
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Full roadmap · basic to pro</h2>
        <FullRoadmap key={d.id} detail={d} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ page

export default function RoadmapsPage() {
  const roadmaps = useQuery({
    queryKey: [...qk.roadmaps, "list"],
    queryFn: () => unwrap(api.GET("/api/v1/roadmaps")),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? roadmaps.data?.[0]?.id ?? null;

  return (
    <>
      <PageHeader
        title="Roadmaps"
        description="Pick a subject and work through it day by day, from basics to pro. Tick today's tasks; progress follows."
        actions={<NewRoadmapDialog onCreated={setSelected} />}
      />
      {roadmaps.isPending ? (
        <LoadingRows rows={3} />
      ) : roadmaps.isError ? (
        <ErrorState error={roadmaps.error} onRetry={() => roadmaps.refetch()} />
      ) : roadmaps.data.length === 0 ? (
        <EmptyState
          icon={Route}
          title="No roadmaps yet"
          description="Start with the built-in DSA roadmap, or type any subject and Claude drafts one."
        />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {roadmaps.data.map((r) => (
              <RoadmapCard key={r.id} roadmap={r} selected={r.id === current} onSelect={() => setSelected(r.id)} />
            ))}
          </div>
          {current ? <RoadmapDetail key={current} id={current} onDeleted={() => setSelected(null)} /> : null}
        </div>
      )}
    </>
  );
}
