"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, CalendarOff, ChevronDown, Flame, Minus, Plus, Repeat, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { addDays, dayLabel, percent } from "@/lib/format";
import { qk } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Habit = Schemas["HabitOut"];
type TodayItem = Schemas["HabitTodayItem"];
type Frequency = "daily" | "days_of_week" | "n_per_week" | "n_per_month";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const STATUS_STYLE: Record<string, string> = {
  met: "bg-primary",
  missed: "bg-destructive/50",
  excused: "bg-amber-400/60",
  rest: "bg-muted",
  pending: "bg-background ring-1 ring-primary/50",
  untracked: "bg-transparent ring-1 ring-border",
};

function scheduleText(schedule: Habit["schedule"]): string {
  if (!schedule) return "No schedule";
  switch (schedule.frequency) {
    case "daily":
      return "Every day";
    case "days_of_week":
      return (schedule.daysOfWeek ?? []).map((d) => WEEKDAYS[d - 1]).join(", ");
    case "n_per_week":
      return `${schedule.timesPerPeriod}× per week`;
    default:
      return `${schedule.timesPerPeriod}× per month`;
  }
}

function useInvalidateHabits() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: qk.habits });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
  };
}

function TodayRow({ item, date }: { item: TodayItem; date: string }) {
  const invalidate = useInvalidateHabits();
  const path = { habit_id: item.habitId, local_date: date };
  const setValue = useMutation({
    mutationFn: async (value: number | null) => {
      if (value === null || value <= 0) {
        await unwrap(api.DELETE("/api/v1/habits/{habit_id}/completions/{local_date}", { params: { path } }));
      } else {
        await unwrap(api.PUT("/api/v1/habits/{habit_id}/completions/{local_date}", { params: { path }, body: { value } }));
      }
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const step = item.measure === "duration" ? 5 : 1;

  return (
    <li className="flex items-center gap-3 py-2">
      {item.measure === "check" ? (
        <Checkbox
          checked={item.done}
          aria-label={`${item.done ? "Undo" : "Complete"} ${item.name}`}
          disabled={setValue.isPending}
          onCheckedChange={() => setValue.mutate(item.done ? null : 1)}
        />
      ) : (
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            variant="outline"
            className="size-7"
            aria-label={`Decrease ${item.name}`}
            disabled={setValue.isPending || item.valueToday <= 0}
            onClick={() => setValue.mutate(Math.max(0, item.valueToday - step))}
          >
            <Minus className="size-3.5" aria-hidden />
          </Button>
          <Button
            size="icon"
            variant="outline"
            className="size-7"
            aria-label={`Increase ${item.name}`}
            disabled={setValue.isPending}
            onClick={() => setValue.mutate(item.valueToday + step)}
          >
            <Plus className="size-3.5" aria-hidden />
          </Button>
        </div>
      )}
      <span className={cn("flex-1 text-sm", item.done && "text-muted-foreground line-through")}>{item.name}</span>
      {item.measure !== "check" ? (
        <span className="tabular text-sm text-muted-foreground">
          <Private>{item.valueToday}</Private> / {item.targetValue} {item.unit ?? (item.measure === "duration" ? "min" : "")}
        </span>
      ) : null}
      {!item.scheduledToday ? <Badge variant="outline">Rest day</Badge> : null}
      {item.currentStreak > 0 ? (
        <span className="flex items-center gap-0.5 text-xs text-amber-600 dark:text-amber-400" title="Current streak">
          <Flame className="size-3.5" aria-hidden />
          <Private>{item.currentStreak}</Private>
          {item.streakUnit === "day" ? "d" : item.streakUnit === "week" ? "w" : "mo"}
        </span>
      ) : null}
    </li>
  );
}

function HistoryStrip({ habitId }: { habitId: string }) {
  const history = useQuery({
    queryKey: [...qk.habits, "history", habitId],
    queryFn: async () => {
      const today = new Date().toLocaleDateString("en-CA");
      return unwrap(
        api.GET("/api/v1/habits/{habit_id}/history", {
          params: { path: { habit_id: habitId }, query: { from: addDays(today, -27), to: today } },
        }),
      );
    },
  });
  if (history.isPending) return <LoadingRows rows={1} />;
  if (history.isError) return <ErrorState error={history.error} />;
  return (
    <div>
      <ol className="grid grid-cols-14 gap-1" aria-label="Last 4 weeks">
        {history.data.days.map((day) => (
          <li
            key={day.date}
            className={cn("aspect-square rounded-sm", STATUS_STYLE[day.status] ?? "bg-muted")}
            title={`${dayLabel(day.date)}: ${day.status}`}
            aria-label={`${dayLabel(day.date)}: ${day.status}`}
          />
        ))}
      </ol>
      <p className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
        {(["met", "missed", "excused", "rest"] as const).map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className={cn("size-2.5 rounded-sm", STATUS_STYLE[s])} aria-hidden /> {s}
          </span>
        ))}
      </p>
    </div>
  );
}

function HabitCard({ habit }: { habit: Habit }) {
  const invalidate = useInvalidateHabits();
  const [open, setOpen] = useState(false);
  const archive = useMutation({
    mutationFn: () =>
      unwrap(api.PATCH("/api/v1/habits/{habit_id}", { params: { path: { habit_id: habit.id } }, body: { archived: true } })),
    onSuccess: () => {
      toast.success(`Archived ${habit.name}`);
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/habits/{habit_id}", { params: { path: { habit_id: habit.id } } })),
    onSuccess: () => {
      toast.success(`Deleted ${habit.name}`);
      invalidate();
    },
  });
  const stats = habit.stats;
  const unit = stats?.streakUnit === "week" ? "weeks" : stats?.streakUnit === "month" ? "months" : "days";

  return (
    <Card>
      <CardHeader>
        <CardTitle>{habit.name}</CardTitle>
        <CardDescription>
          {scheduleText(habit.schedule)}
          {habit.measure !== "check" ? ` · target ${habit.targetValue} ${habit.unit ?? ""}` : ""}
        </CardDescription>
        <CardAction className="flex gap-1">
          <Button variant="ghost" size="icon" aria-label={`Archive ${habit.name}`} onClick={() => archive.mutate()}>
            <Archive className="size-4" aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" aria-label={`Delete ${habit.name}`} onClick={() => remove.mutate()}>
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-md bg-muted/50 p-2">
            <dd className="tabular text-xl font-semibold"><Private>{stats?.currentStreak ?? 0}</Private></dd>
            <dt className="text-xs text-muted-foreground">current ({unit})</dt>
          </div>
          <div className="rounded-md bg-muted/50 p-2">
            <dd className="tabular text-xl font-semibold"><Private>{stats?.longestStreak ?? 0}</Private></dd>
            <dt className="text-xs text-muted-foreground">longest</dt>
          </div>
          <div className="rounded-md bg-muted/50 p-2">
            <dd className="tabular text-xl font-semibold"><Private>{percent(stats?.consistency)}</Private></dd>
            <dt className="text-xs text-muted-foreground">30-day consistency</dt>
          </div>
        </dl>
        <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
          <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden />
          {open ? "Hide history" : "Show last 4 weeks"}
        </Button>
        {open ? <HistoryStrip habitId={habit.id} /> : null}
      </CardContent>
    </Card>
  );
}

function NewHabitDialog() {
  const invalidate = useInvalidateHabits();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [measure, setMeasure] = useState<"check" | "count" | "duration">("check");
  const [target, setTarget] = useState("8");
  const [unit, setUnit] = useState("");
  const [frequency, setFrequency] = useState<Frequency>("daily");
  const [days, setDays] = useState<number[]>([1, 3, 5]);
  const [times, setTimes] = useState("3");

  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/habits", {
          body: {
            name: name.trim(),
            measure,
            targetValue: measure === "check" ? 1 : Number(target),
            unit: measure === "check" ? null : unit || (measure === "duration" ? "min" : null),
            schedule: {
              frequency,
              daysOfWeek: frequency === "days_of_week" ? days : null,
              timesPerPeriod: frequency.startsWith("n_per") ? Number(times) : null,
            },
          },
        }),
      ),
    onSuccess: () => {
      toast.success("Habit created");
      invalidate();
      setOpen(false);
      setName("");
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" aria-hidden /> New habit
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New habit</DialogTitle>
          <DialogDescription>Pick what counts as done and when it is due.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="habit-name">Name</Label>
            <Input id="habit-name" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Read 20 minutes" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label>Measure</Label>
              <Select value={measure} onValueChange={(v) => setMeasure(v as typeof measure)}>
                <SelectTrigger className="w-full" aria-label="Measure"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="check">Done / not done</SelectItem>
                  <SelectItem value="count">Count</SelectItem>
                  <SelectItem value="duration">Minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {measure !== "check" ? (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="habit-target">Target</Label>
                  <Input id="habit-target" type="number" min={1} value={target} onChange={(e) => setTarget(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="habit-unit">Unit</Label>
                  <Input id="habit-unit" maxLength={20} value={unit} placeholder={measure === "duration" ? "min" : "glasses"} onChange={(e) => setUnit(e.target.value)} />
                </div>
              </>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label>How often</Label>
            <Select value={frequency} onValueChange={(v) => setFrequency(v as Frequency)}>
              <SelectTrigger className="w-full" aria-label="How often"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="daily">Every day</SelectItem>
                <SelectItem value="days_of_week">Specific weekdays</SelectItem>
                <SelectItem value="n_per_week">A number of times per week</SelectItem>
                <SelectItem value="n_per_month">A number of times per month</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {frequency === "days_of_week" ? (
            <fieldset className="flex flex-wrap gap-1">
              <legend className="sr-only">Weekdays</legend>
              {WEEKDAYS.map((label, i) => {
                const day = i + 1;
                const on = days.includes(day);
                return (
                  <Button
                    key={label}
                    type="button"
                    size="sm"
                    variant={on ? "default" : "outline"}
                    aria-pressed={on}
                    onClick={() => setDays(on ? days.filter((d) => d !== day) : [...days, day].sort())}
                  >
                    {label}
                  </Button>
                );
              })}
            </fieldset>
          ) : null}
          {frequency.startsWith("n_per") ? (
            <div className="space-y-1.5">
              <Label htmlFor="habit-times">Times per {frequency === "n_per_week" ? "week" : "month"}</Label>
              <Input id="habit-times" type="number" min={1} max={frequency === "n_per_week" ? 7 : 31} value={times} onChange={(e) => setTimes(e.target.value)} />
            </div>
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? "Creating…" : "Create habit"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BreaksCard({ habits }: { habits: Habit[] }) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateHabits();
  const breaks = useQuery({
    queryKey: qk.habitExceptions,
    queryFn: () => unwrap(api.GET("/api/v1/habit-exceptions")),
  });
  const today = new Date().toLocaleDateString("en-CA");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [kind, setKind] = useState<"vacation" | "sick" | "rest" | "travel" | "other">("rest");
  const [habitId, setHabitId] = useState("all");

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: qk.habitExceptions });
    invalidate();
  };
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/habit-exceptions", {
          body: { startDate: start, endDate: end, kind, habitId: habitId === "all" ? null : habitId },
        }),
      ),
    onSuccess: () => {
      toast.success("Break added. Streaks are protected for those days.");
      refresh();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/habit-exceptions/{exception_id}", { params: { path: { exception_id: id } } })),
    onSuccess: refresh,
  });
  const nameOf = (id: string | null | undefined) => (id ? habits.find((h) => h.id === id)?.name ?? "A habit" : "All habits");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarOff className="size-4 text-primary" aria-hidden /> Breaks
        </CardTitle>
        <CardDescription>Vacation, illness or rest days never break a streak.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="grid gap-2 sm:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <Input type="date" aria-label="Start date" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input type="date" aria-label="End date" value={end} onChange={(e) => setEnd(e.target.value)} />
          <Select value={kind} onValueChange={(v) => setKind(v as typeof kind)}>
            <SelectTrigger className="w-full" aria-label="Reason"><SelectValue /></SelectTrigger>
            <SelectContent>
              {(["rest", "vacation", "sick", "travel", "other"] as const).map((k) => (
                <SelectItem key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={habitId} onValueChange={setHabitId}>
            <SelectTrigger className="w-full" aria-label="Applies to"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All habits</SelectItem>
              {habits.map((h) => (
                <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button type="submit" variant="outline" disabled={create.isPending}>Add break</Button>
        </form>
        {breaks.data && breaks.data.length > 0 ? (
          <ul className="divide-y text-sm">
            {breaks.data.map((b) => (
              <li key={b.id} className="flex items-center gap-2 py-2">
                <Badge variant="secondary">{b.kind}</Badge>
                <span className="flex-1">
                  {dayLabel(b.startDate)}
                  {b.endDate !== b.startDate ? ` – ${dayLabel(b.endDate)}` : ""} · {nameOf(b.habitId)}
                </span>
                <Button variant="ghost" size="icon" aria-label="Remove break" onClick={() => remove.mutate(b.id)}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function HabitsPage() {
  const today = useQuery({
    queryKey: [...qk.habits, "today"],
    queryFn: () => unwrap(api.GET("/api/v1/habits/today")),
  });
  const habits = useQuery({
    queryKey: [...qk.habits, "list"],
    queryFn: () => unwrap(api.GET("/api/v1/habits")),
  });

  return (
    <>
      <PageHeader
        title="Habits"
        description="Small daily wins. Breaks you plan for never count against you."
        actions={<NewHabitDialog />}
      />
      <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
        <Card className="self-start">
          <CardHeader>
            <CardTitle>Today</CardTitle>
            <CardDescription>
              {today.data ? `${today.data.completed} of ${today.data.scheduled} done` : "Loading…"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {today.isPending ? (
              <LoadingRows />
            ) : today.isError ? (
              <ErrorState error={today.error} onRetry={() => today.refetch()} />
            ) : today.data.items.length === 0 ? (
              <EmptyState icon={Repeat} title="No habits yet" description="Create your first habit to start a streak." />
            ) : (
              <ul className="divide-y">
                {today.data.items.map((item) => (
                  <TodayRow key={item.habitId} item={item} date={today.data.date} />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          {habits.isPending ? (
            <LoadingRows rows={4} />
          ) : habits.isError ? (
            <ErrorState error={habits.error} onRetry={() => habits.refetch()} />
          ) : (
            <>
              <div className="grid gap-4 xl:grid-cols-2">
                {habits.data.map((habit) => (
                  <HabitCard key={habit.id} habit={habit} />
                ))}
              </div>
              <BreaksCard habits={habits.data} />
            </>
          )}
        </div>
      </div>
    </>
  );
}
