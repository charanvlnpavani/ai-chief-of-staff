"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, CheckCircle2, ChevronDown, Pause, Play, Plus, Target, Trash2, X } from "lucide-react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { dayLabel, percent } from "@/lib/format";
import { qk } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Goal = Schemas["GoalOut"];
type GoalDetail = Schemas["GoalDetailOut"];
type Health = Goal["progress"]["health"];
type GoalUpdate = Schemas["GoalUpdate"];
type Entry = Schemas["EntryOut"];

const HEALTH: { key: Health; label: string; badge: string }[] = [
  { key: "at_risk", label: "At risk", badge: "bg-destructive/10 text-destructive" },
  { key: "on_track", label: "On track", badge: "bg-primary/10 text-primary" },
  { key: "not_started", label: "Not started", badge: "border text-muted-foreground" },
  { key: "paused", label: "Paused", badge: "bg-muted text-muted-foreground" },
  { key: "completed", label: "Completed", badge: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
];
const ARCHIVED = { key: "archived" as Health, label: "Archived", badge: "bg-muted text-muted-foreground" };

function num(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function deadlineText(goal: Goal): string {
  const left = goal.progress.daysLeft;
  if (!goal.targetDate || left === null || left === undefined) return "No target date";
  if (left < 0) return `${-left} days past ${dayLabel(goal.targetDate)}`;
  if (left === 0) return "Due today";
  return `${left} days left · ${dayLabel(goal.targetDate)}`;
}

function useGoalCache() {
  const queryClient = useQueryClient();
  return (detail?: GoalDetail) => {
    if (detail) queryClient.setQueryData([...qk.goals, "detail", detail.id], detail);
    void queryClient.invalidateQueries({ queryKey: [...qk.goals, "list"] });
  };
}

function patchGoal(goalId: string, body: GoalUpdate) {
  return unwrap(api.PATCH("/api/v1/goals/{goal_id}", { params: { path: { goal_id: goalId } }, body }));
}

/** Updates a goal. Callers send `version`; a 409 means it changed elsewhere, so reload it. */
function useUpdateGoal(goal: Goal) {
  const queryClient = useQueryClient();
  const refresh = useGoalCache();
  return useMutation({
    mutationFn: (body: GoalUpdate) => patchGoal(goal.id, body),
    onSuccess: refresh,
    onError: (error) => {
      if (error instanceof ApiError && error.code === "version_conflict") {
        toast.error("This goal changed in another tab. Showing the latest version.");
        void queryClient.invalidateQueries({ queryKey: qk.goals });
      } else {
        toast.error(errorMessage(error));
      }
    },
  });
}

function Milestones({ goal }: { goal: GoalDetail }) {
  const refresh = useGoalCache();
  const [title, setTitle] = useState("");
  const path = { goal_id: goal.id };
  const add = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/goals/{goal_id}/milestones", { params: { path }, body: { title: title.trim() } })),
    onSuccess: (detail) => {
      refresh(detail);
      setTitle("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const toggle = useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      unwrap(
        api.PATCH("/api/v1/goals/{goal_id}/milestones/{milestone_id}", {
          params: { path: { ...path, milestone_id: id } },
          body: { done },
        }),
      ),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/goals/{goal_id}/milestones/{milestone_id}", { params: { path: { ...path, milestone_id: id } } })),
    onSuccess: refresh,
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">Milestones</h3>
      {goal.milestones.length > 0 ? (
        <ul className="divide-y">
          {goal.milestones.map((m) => {
            const done = Boolean(m.completedAt);
            return (
              <li key={m.id} className="flex items-center gap-3 py-1.5">
                <Checkbox
                  checked={done}
                  aria-label={`${done ? "Reopen" : "Complete"} ${m.title}`}
                  disabled={toggle.isPending}
                  onCheckedChange={() => toggle.mutate({ id: m.id, done: !done })}
                />
                <span className={cn("flex-1 text-sm", done && "text-muted-foreground line-through")}>{m.title}</span>
                {m.dueDate ? <span className="text-xs text-muted-foreground">{dayLabel(m.dueDate)}</span> : null}
                <Button variant="ghost" size="icon" className="size-7" aria-label={`Remove ${m.title}`} onClick={() => remove.mutate(m.id)}>
                  <X className="size-3.5" aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No milestones yet. Break the goal into a few concrete steps.</p>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (title.trim()) add.mutate();
        }}
      >
        <Input aria-label="New milestone" placeholder="Add a milestone" maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
        <Button type="submit" variant="outline" disabled={!title.trim() || add.isPending}>
          Add
        </Button>
      </form>
    </section>
  );
}

function CheckInForm({ goal }: { goal: GoalDetail }) {
  const refresh = useGoalCache();
  const numeric = goal.progressRule === "numeric";
  const { hidden } = usePrivacy();
  // In privacy mode the current total is not pre-filled, so it cannot be read off the input.
  const [value, setValue] = useState(hidden ? "" : (goal.progress.currentValue?.toString() ?? ""));
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/goals/{goal_id}/check-ins", {
          params: { path: { goal_id: goal.id } },
          body: { value: numeric && value !== "" ? Number(value) : null, note: note.trim() || null },
        }),
      ),
    onSuccess: (detail) => {
      toast.success("Check-in saved");
      refresh(detail);
      setNote("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const canSave = (numeric && value !== "") || note.trim() !== "";

  return (
    <form
      className="space-y-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave) save.mutate();
      }}
    >
      <h3 className="text-sm font-medium">Check in</h3>
      {numeric ? (
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor={`value-${goal.id}`} className="shrink-0 text-sm text-muted-foreground">
            Current total
          </Label>
          <Input id={`value-${goal.id}`} type="number" step="0.01" className="w-32" value={value} onChange={(e) => setValue(e.target.value)} />
          <span className="text-sm text-muted-foreground">
            of {num(goal.targetValue)} {goal.unit ?? ""}
          </span>
        </div>
      ) : null}
      <Textarea aria-label="Note" placeholder="What moved forward? What is in the way?" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      <Button type="submit" size="sm" disabled={!canSave || save.isPending}>
        {save.isPending ? "Saving…" : "Save check-in"}
      </Button>
    </form>
  );
}

function History({ goal }: { goal: GoalDetail }) {
  const [older, setOlder] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState(goal.entriesNextCursor ?? null);
  const loadOlder = useMutation({
    mutationFn: (from: string) =>
      unwrap(
        api.GET("/api/v1/goals/{goal_id}/entries", {
          params: { path: { goal_id: goal.id }, query: { cursor: from } },
        }),
      ),
    onSuccess: (page) => {
      setOlder((current) => [...current, ...page.items]);
      setCursor(page.nextCursor ?? null);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const entries = [...goal.entries, ...older];
  if (entries.length === 0) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">History</h3>
      <ol className="max-h-56 space-y-1.5 overflow-y-auto text-sm">
        {entries.map((e) => (
          <li key={e.id} className="flex gap-3">
            <span className="w-24 shrink-0 text-xs leading-5 text-muted-foreground">{dayLabel(e.localDate)}</span>
            <span className="flex-1">
              {e.kind === "check_in" && e.value !== null && e.value !== undefined ? (
                <span className="tabular font-medium">
                  <Private>{num(e.value)}</Private>
                  {e.targetValue !== null && e.targetValue !== undefined ? ` / ${num(e.targetValue)}` : ""} {goal.unit ?? ""}
                </span>
              ) : null}
              {e.kind !== "check_in" ? <Badge variant="outline" className="mr-1">{e.kind === "target_change" ? "Target changed" : "Status"}</Badge> : null}
              {e.note ? <span className="text-muted-foreground"> <Private>{e.note}</Private></span> : null}
            </span>
          </li>
        ))}
      </ol>
      {cursor ? (
        <Button variant="ghost" size="sm" disabled={loadOlder.isPending} onClick={() => loadOlder.mutate(cursor)}>
          {loadOlder.isPending ? "Loading…" : "Show older"}
        </Button>
      ) : null}
    </section>
  );
}

function EditTarget({ goal }: { goal: GoalDetail }) {
  const update = useUpdateGoal(goal);
  const [target, setTarget] = useState(goal.targetValue?.toString() ?? "");
  const [targetDate, setTargetDate] = useState(goal.targetDate ?? "");
  const dirty = target !== (goal.targetValue?.toString() ?? "") || targetDate !== (goal.targetDate ?? "");
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate({
          version: goal.version,
          targetDate: targetDate || null,
          ...(goal.progressRule === "numeric" && target !== "" ? { targetValue: Number(target) } : {}),
        });
      }}
    >
      {goal.progressRule === "numeric" ? (
        <div className="space-y-1">
          <Label htmlFor={`target-${goal.id}`} className="text-xs text-muted-foreground">Target</Label>
          <Input id={`target-${goal.id}`} type="number" step="0.01" className="w-28" value={target} onChange={(e) => setTarget(e.target.value)} />
        </div>
      ) : null}
      <div className="space-y-1">
        <Label htmlFor={`date-${goal.id}`} className="text-xs text-muted-foreground">Target date</Label>
        <Input id={`date-${goal.id}`} type="date" className="w-40" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
      </div>
      <Button type="submit" size="sm" variant="outline" disabled={!dirty || update.isPending}>
        Update target
      </Button>
      <p className="w-full text-xs text-muted-foreground">Earlier check-ins stay in the history when you change the target.</p>
    </form>
  );
}

function GoalDetails({ goalId }: { goalId: string }) {
  const detail = useQuery({
    queryKey: [...qk.goals, "detail", goalId],
    queryFn: () => unwrap(api.GET("/api/v1/goals/{goal_id}", { params: { path: { goal_id: goalId } } })),
  });
  if (detail.isPending) return <LoadingRows rows={3} />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const goal = detail.data;
  return (
    <div className="space-y-5 border-t pt-4">
      {goal.description ? <p className="text-sm text-muted-foreground">{goal.description}</p> : null}
      <Milestones goal={goal} />
      <CheckInForm key={goal.version} goal={goal} />
      <EditTarget key={`t-${goal.targetValue}-${goal.targetDate}`} goal={goal} />
      <History key={goal.entries[0]?.id ?? "empty"} goal={goal} />
    </div>
  );
}

function GoalCard({ goal }: { goal: Goal }) {
  const [open, setOpen] = useState(false);
  const refresh = useGoalCache();
  const update = useUpdateGoal(goal);
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/goals/{goal_id}", { params: { path: { goal_id: goal.id } } })),
    onSuccess: () => {
      toast.success(`Deleted ${goal.title}`);
      refresh();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const queryClient = useQueryClient();
  const archive = useMutation({
    mutationFn: () => patchGoal(goal.id, { status: "archived", version: goal.version }),
    onSuccess: (detail) => {
      refresh(detail);
      toast.success(`Archived ${goal.title}`, {
        action: {
          label: "Undo",
          onClick: () => {
            patchGoal(goal.id, { status: goal.status, version: detail.version })
              .then((restored) => refresh(restored))
              .catch((error: unknown) => {
                toast.error(errorMessage(error));
                void queryClient.invalidateQueries({ queryKey: qk.goals });
              });
          },
        },
      });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const archived = goal.status === "archived";
  const { hidden } = usePrivacy();
  const p = goal.progress;
  const health = HEALTH.find((h) => h.key === p.health) ?? ARCHIVED;
  const isNumeric = goal.progressRule === "numeric";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          {goal.title}
          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", health.badge)}>{health.label}</span>
        </CardTitle>
        <CardDescription>
          {[goal.category, goal.importance === "high" ? "High importance" : null, deadlineText(goal)].filter(Boolean).join(" · ")}
        </CardDescription>
        <CardAction className="flex gap-1">
          {archived ? (
            <Button variant="ghost" size="icon" aria-label={`Restore ${goal.title}`} title="Restore" disabled={update.isPending} onClick={() => update.mutate({ status: "active", version: goal.version })}>
              <ArchiveRestore className="size-4" aria-hidden />
            </Button>
          ) : (
            <>
              {goal.status === "active" ? (
                <Button variant="ghost" size="icon" aria-label={`Pause ${goal.title}`} title="Pause" disabled={update.isPending} onClick={() => update.mutate({ status: "paused", version: goal.version })}>
                  <Pause className="size-4" aria-hidden />
                </Button>
              ) : (
                <Button variant="ghost" size="icon" aria-label={`Reopen ${goal.title}`} title={goal.status === "completed" ? "Reopen" : "Resume"} disabled={update.isPending} onClick={() => update.mutate({ status: "active", version: goal.version })}>
                  <Play className="size-4" aria-hidden />
                </Button>
              )}
              {goal.status !== "completed" ? (
                <Button variant="ghost" size="icon" aria-label={`Mark ${goal.title} completed`} title="Mark completed" disabled={update.isPending} onClick={() => update.mutate({ status: "completed", version: goal.version })}>
                  <CheckCircle2 className="size-4" aria-hidden />
                </Button>
              ) : null}
              <Button variant="ghost" size="icon" aria-label={`Archive ${goal.title}`} title="Archive" disabled={archive.isPending} onClick={() => archive.mutate()}>
                <Archive className="size-4" aria-hidden />
              </Button>
            </>
          )}
          <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={`Delete ${goal.title}`} title="Delete">
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Delete “{goal.title}”?</DialogTitle>
                <DialogDescription>
                  Its milestones and check-in history disappear from Personal OS. To keep them, archive the goal instead.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(undefined, { onSettled: () => setConfirmDelete(false) })}
                >
                  {remove.isPending ? "Deleting…" : "Delete goal"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <div className="flex items-baseline justify-between text-sm">
            <span className="tabular text-lg font-semibold">
              <Private>{percent(p.percent)}</Private>
            </span>
            <span className="tabular text-muted-foreground">
              {isNumeric ? (
                <>
                  <Private>{num(p.currentValue ?? goal.startValue)}</Private> / {num(goal.targetValue)} {goal.unit ?? ""}
                </>
              ) : (
                <>
                  <Private>{p.milestonesDone}</Private> of {p.milestonesTotal} milestones
                </>
              )}
            </span>
          </div>
          <Progress value={hidden ? 0 : Math.round((p.percent ?? 0) * 100)} aria-label={`${goal.title} progress`} />
          {p.expected !== null && p.expected !== undefined && goal.status === "active" ? (
            <p className="text-xs text-muted-foreground">
              {percent(p.expected)} of the time has passed
              {p.lastCheckIn ? ` · last check-in ${dayLabel(p.lastCheckIn)}` : " · no check-ins yet"}
            </p>
          ) : null}
          {goal.successMetric ? <p className="text-xs text-muted-foreground">Success: {goal.successMetric}</p> : null}
        </div>
        {archived ? (
          <p className="text-xs text-muted-foreground">Archived. Restore it to check in or change milestones.</p>
        ) : (
          <>
            <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
              <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
              {open ? "Hide details" : "Milestones, check-ins & history"}
            </Button>
            {open ? <GoalDetails goalId={goal.id} /> : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function NewGoalDialog() {
  const refresh = useGoalCache();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [importance, setImportance] = useState<"low" | "medium" | "high">("medium");
  const [rule, setRule] = useState<"milestones" | "numeric">("numeric");
  const [startValue, setStartValue] = useState("0");
  const [targetValue, setTargetValue] = useState("");
  const [unit, setUnit] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [metric, setMetric] = useState("");
  const [milestones, setMilestones] = useState("");

  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/goals", {
          body: {
            title: title.trim(),
            category: category.trim() || null,
            importance,
            successMetric: metric.trim() || null,
            targetDate: targetDate || null,
            progressRule: rule,
            startValue: rule === "numeric" ? Number(startValue || 0) : 0,
            targetValue: rule === "numeric" ? Number(targetValue) : null,
            unit: rule === "numeric" ? unit.trim() || null : null,
            milestones: milestones
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
              .map((line) => ({ title: line.slice(0, 200) })),
          },
        }),
      ),
    onSuccess: (detail) => {
      toast.success("Goal created");
      refresh(detail);
      setOpen(false);
      setTitle("");
      setTargetValue("");
      setMilestones("");
      setMetric("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const valid = title.trim() !== "" && (rule === "milestones" || (targetValue !== "" && Number(targetValue) !== Number(startValue || 0)));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" aria-hidden /> New goal
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New goal</DialogTitle>
          <DialogDescription>Make it measurable: a number to reach, or milestones to finish.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="goal-title">Goal</Label>
            <Input id="goal-title" required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Read 24 books this year" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="goal-category">Category</Label>
              <Input id="goal-category" maxLength={40} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Learning" />
            </div>
            <div className="space-y-1.5">
              <Label>Importance</Label>
              <Select value={importance} onValueChange={(v) => setImportance(v as typeof importance)}>
                <SelectTrigger className="w-full" aria-label="Importance"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Measure progress by</Label>
            <Select value={rule} onValueChange={(v) => setRule(v as typeof rule)}>
              <SelectTrigger className="w-full" aria-label="Measure progress by"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="numeric">A number (books, km, kg, ₹ saved…)</SelectItem>
                <SelectItem value="milestones">Milestones completed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {rule === "numeric" ? (
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="goal-start">Start</Label>
                <Input id="goal-start" type="number" step="0.01" value={startValue} onChange={(e) => setStartValue(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="goal-target">Target</Label>
                <Input id="goal-target" type="number" step="0.01" required value={targetValue} onChange={(e) => setTargetValue(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="goal-unit">Unit</Label>
                <Input id="goal-unit" maxLength={20} value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="books" />
              </div>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="goal-date">Target date (optional)</Label>
            <Input id="goal-date" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="goal-metric">What does success look like? (optional)</Label>
            <Input id="goal-metric" maxLength={200} value={metric} onChange={(e) => setMetric(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="goal-milestones">Milestones (one per line, optional)</Label>
            <Textarea id="goal-milestones" value={milestones} onChange={(e) => setMilestones(e.target.value)} placeholder={"Finish chapter 1\nShare a draft"} />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!valid || create.isPending}>
              {create.isPending ? "Creating…" : "Create goal"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function GoalsPage() {
  const [showArchived, setShowArchived] = useState(false);
  const goals = useQuery({
    queryKey: [...qk.goals, "list", { showArchived }],
    queryFn: () => unwrap(api.GET("/api/v1/goals", { params: { query: { include_archived: showArchived } } })),
  });
  const active = goals.data?.filter((g) => g.status !== "archived") ?? [];
  const archived = goals.data?.filter((g) => g.status === "archived") ?? [];

  return (
    <>
      <PageHeader
        title="Goals"
        description="Long-term ambitions, broken into steps. Progress comes from what you record, never from a guess."
        actions={
          <>
            <Button variant="outline" aria-pressed={showArchived} onClick={() => setShowArchived(!showArchived)}>
              <Archive className="size-4" aria-hidden /> {showArchived ? "Hide archived" : "Show archived"}
            </Button>
            <NewGoalDialog />
          </>
        }
      />
      {goals.isPending ? (
        <LoadingRows rows={4} />
      ) : goals.isError ? (
        <ErrorState error={goals.error} onRetry={() => goals.refetch()} />
      ) : goals.data.length === 0 ? (
        <EmptyState
          icon={Target}
          title={showArchived ? "No goals yet" : "No active goals"}
          description="Create a goal with a number to reach or milestones to finish."
        />
      ) : (
        <div className="space-y-6">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {HEALTH.map((h) => (
              <div key={h.key} className="rounded-lg border p-3">
                <dd className="tabular text-2xl font-semibold">
                  <Private>{active.filter((g) => g.progress.health === h.key).length}</Private>
                </dd>
                <dt className="text-xs text-muted-foreground">{h.label}</dt>
              </div>
            ))}
          </dl>
          {[...HEALTH, ARCHIVED].map((h) => {
            const group = (h.key === "archived" ? archived : active).filter((g) => g.progress.health === h.key);
            if (group.length === 0) return null;
            return (
              <section key={h.key} aria-labelledby={`group-${h.key}`} className="space-y-3">
                <h2 id={`group-${h.key}`} className="text-sm font-medium text-muted-foreground">
                  {h.label} · <Private>{group.length}</Private>
                </h2>
                <div className="grid gap-4 lg:grid-cols-2">
                  {group.map((goal) => (
                    <GoalCard key={goal.id} goal={goal} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}
