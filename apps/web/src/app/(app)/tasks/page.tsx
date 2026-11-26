"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Pencil, Plus, Repeat, Search, Trash2 } from "lucide-react";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { addDays, dueLabel } from "@/lib/format";
import { qk } from "@/lib/queries";

type Task = Schemas["TaskOut"];
type View = "today" | "upcoming" | "overdue" | "completed" | "all";

const VIEWS: { value: View; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "upcoming", label: "Upcoming" },
  { value: "overdue", label: "Overdue" },
  { value: "completed", label: "Completed" },
  { value: "all", label: "All" },
];
const RECURRENCE = [
  { value: "none", label: "Does not repeat" },
  { value: "FREQ=DAILY", label: "Every day" },
  { value: "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", label: "Every weekday" },
  { value: "FREQ=WEEKLY", label: "Every week" },
  { value: "FREQ=MONTHLY", label: "Every month" },
];
const PRIORITY_LABEL: Record<number, string> = { 1: "P1 · Urgent", 2: "P2 · High", 3: "P3 · Normal", 4: "P4 · Low" };

function todayIso() {
  // The API decides "today" in the user's time zone; this is only a default for the date picker.
  return new Date().toLocaleDateString("en-CA");
}

function EditTaskDialog({ task, onClose }: { task: Task; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(task.title);
  const [notes, setNotes] = useState(task.notes ?? "");
  const [dueOn, setDueOn] = useState(task.dueOn ?? "");
  const [priority, setPriority] = useState(String(task.priority));
  const [recurrence, setRecurrence] = useState(task.recurrenceRule ?? "none");

  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/tasks/{task_id}", {
          params: { path: { task_id: task.id } },
          body: {
            title,
            notes: notes || null,
            dueOn: dueOn || null,
            priority: Number(priority),
            recurrenceRule: recurrence === "none" ? null : recurrence,
            version: task.version,
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.tasks });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard });
      toast.success("Task saved");
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit task</DialogTitle>
          <DialogDescription>Changes are saved to your task list.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="task-title">Title</Label>
            <Input id="task-title" value={title} maxLength={500} required onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="task-notes">Notes</Label>
            <Textarea id="task-notes" value={notes} rows={3} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="task-due">Due date</Label>
              <Input id="task-due" type="date" value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger className="w-full" aria-label="Priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[1, 2, 3, 4].map((p) => (
                    <SelectItem key={p} value={String(p)}>
                      {PRIORITY_LABEL[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Repeat</Label>
            <Select value={recurrence} onValueChange={setRecurrence}>
              <SelectTrigger className="w-full" aria-label="Repeat">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RECURRENCE.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending || !title.trim()}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TasksContent() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<View>("today");
  const [search, setSearch] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState<"today" | "tomorrow" | "none">("today");
  const [editing, setEditing] = useState<Task | null>(null);

  const tasks = useQuery({
    queryKey: [...qk.tasks, view, search],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/tasks", {
          params: { query: { view, q: search || undefined, limit: 100 } },
        }),
      ),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: qk.tasks });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
  };

  const create = useMutation({
    mutationFn: () => {
      const today = todayIso();
      const dueOn = due === "today" ? today : due === "tomorrow" ? addDays(today, 1) : null;
      return unwrap(api.POST("/api/v1/tasks", { body: { title: title.trim(), dueOn } }));
    },
    onSuccess: () => {
      setTitle("");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const complete = useMutation({
    mutationFn: async (task: Task): Promise<void> => {
      const path = { task_id: task.id };
      if (task.status === "done") {
        await unwrap(api.PATCH("/api/v1/tasks/{task_id}", { params: { path }, body: { status: "todo" } }));
      } else {
        await unwrap(api.POST("/api/v1/tasks/{task_id}/complete", { params: { path } }));
      }
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (task: Task) =>
      unwrap(api.DELETE("/api/v1/tasks/{task_id}", { params: { path: { task_id: task.id } } })),
    onSuccess: () => {
      toast.success("Task deleted");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const today = todayIso();

  return (
    <>
      <PageHeader title="Tasks" description="Everything you need to do, across every part of life." />
      <Card className="mb-4">
        <CardContent>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (title.trim()) create.mutate();
            }}
          >
            <Label htmlFor="quick-add" className="sr-only">
              New task
            </Label>
            <Input
              id="quick-add"
              placeholder="Add a task…"
              value={title}
              maxLength={500}
              onChange={(e) => setTitle(e.target.value)}
              className="min-w-48 flex-1"
            />
            <Select value={due} onValueChange={(v) => setDue(v as typeof due)}>
              <SelectTrigger className="w-32" aria-label="Due">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="today">Today</SelectItem>
                <SelectItem value="tomorrow">Tomorrow</SelectItem>
                <SelectItem value="none">No date</SelectItem>
              </SelectContent>
            </Select>
            <Button type="submit" disabled={!title.trim() || create.isPending}>
              <Plus className="size-4" aria-hidden /> Add
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Tabs value={view} onValueChange={(v) => setView(v as View)}>
          <TabsList>
            {VIEWS.map((v) => (
              <TabsTrigger key={v.value} value={v.value}>
                {v.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            aria-label="Search tasks"
            placeholder="Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-48 pl-8"
          />
        </div>
      </div>

      {tasks.isPending ? (
        <LoadingRows rows={5} />
      ) : tasks.isError ? (
        <ErrorState error={tasks.error} onRetry={() => tasks.refetch()} />
      ) : tasks.data.items.length === 0 ? (
        <EmptyState
          icon={CheckSquare}
          title={search ? "No matching tasks" : "Nothing here"}
          description={view === "today" ? "Nothing due today or overdue. Add one above." : undefined}
        />
      ) : (
        <ul className="divide-y rounded-lg border">
          {tasks.data.items.map((task) => {
            const label = dueLabel(task.dueOn, today);
            const done = task.status === "done";
            return (
              <li key={task.id} className="flex items-center gap-3 px-3 py-2.5">
                <Checkbox
                  checked={done}
                  aria-label={done ? `Reopen ${task.title}` : `Complete ${task.title}`}
                  onCheckedChange={() => complete.mutate(task)}
                />
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-sm ${done ? "text-muted-foreground line-through" : ""}`}>{task.title}</p>
                  {task.notes ? <p className="truncate text-xs text-muted-foreground">{task.notes}</p> : null}
                </div>
                {task.recurrenceRule ? <Repeat className="size-3.5 text-muted-foreground" aria-label="Repeats" /> : null}
                {task.priority <= 2 ? (
                  <Badge variant={task.priority === 1 ? "destructive" : "secondary"}>P{task.priority}</Badge>
                ) : null}
                {label ? (
                  <span className={`hidden text-xs sm:inline ${label.includes("overdue") ? "text-destructive" : "text-muted-foreground"}`}>
                    {label}
                  </span>
                ) : null}
                <Button variant="ghost" size="icon" aria-label={`Edit ${task.title}`} onClick={() => setEditing(task)}>
                  <Pencil className="size-4" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${task.title}`}
                  onClick={() => remove.mutate(task)}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {editing ? <EditTaskDialog task={editing} onClose={() => setEditing(null)} /> : null}
    </>
  );
}

// "Today" is read on each visit, so the page streams in after the static shell.
export default function TasksPage() {
  return (
    <Suspense fallback={<LoadingRows rows={5} />}>
      <TasksContent />
    </Suspense>
  );
}
