"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, CheckSquare, Flame, Repeat, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
import { EmptyState, ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { dayLabel, dueLabel, formatMinutes, greeting } from "@/lib/format";
import { qk, useMe } from "@/lib/queries";

type Dashboard = Schemas["DashboardOut"];

function useInvalidateToday() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
    void queryClient.invalidateQueries({ queryKey: qk.tasks });
    void queryClient.invalidateQueries({ queryKey: qk.habits });
  };
}

function PriorityTasks({ data }: { data: Dashboard }) {
  const invalidate = useInvalidateToday();
  const complete = useMutation({
    mutationFn: (taskId: string) =>
      unwrap(api.POST("/api/v1/tasks/{task_id}/complete", { params: { path: { task_id: taskId } } })),
    onSuccess: (result) => {
      toast.success(`Done: ${result.task.title}`, {
        description: result.nextTask ? `Next one is due ${dueLabel(result.nextTask.dueOn, data.date)}` : undefined,
      });
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const { counts, top } = data.tasks;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckSquare className="size-4 text-primary" aria-hidden /> Priority tasks
        </CardTitle>
        <CardDescription>
          <Private>{counts.dueToday}</Private> due today · <Private>{counts.overdue}</Private> overdue ·{" "}
          <Private>{counts.completedToday}</Private> done
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/tasks">All tasks</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {top.length === 0 ? (
          <EmptyState icon={CheckSquare} title="Nothing due" description="Add a task or enjoy the space." />
        ) : (
          <ul className="space-y-1">
            {top.map((task) => {
              const due = dueLabel(task.dueOn, data.date);
              return (
                <li key={task.id} className="flex items-center gap-3 rounded-md px-1 py-1.5 hover:bg-muted/50">
                  <Checkbox
                    aria-label={`Complete ${task.title}`}
                    disabled={complete.isPending}
                    onCheckedChange={() => complete.mutate(task.id)}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{task.title}</span>
                  {task.priority === 1 ? <Badge variant="destructive">P1</Badge> : null}
                  {due ? (
                    <span className={`text-xs ${due.includes("overdue") ? "text-destructive" : "text-muted-foreground"}`}>
                      {due}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function HabitsToday({ data }: { data: Dashboard }) {
  const invalidate = useInvalidateToday();
  const toggle = useMutation({
    mutationFn: async ({ habitId, done }: { habitId: string; done: boolean }) => {
      const path = { habit_id: habitId, local_date: data.date };
      if (done) {
        await unwrap(api.DELETE("/api/v1/habits/{habit_id}/completions/{local_date}", { params: { path } }));
      } else {
        await unwrap(api.PUT("/api/v1/habits/{habit_id}/completions/{local_date}", { params: { path } }));
      }
    },
    onSuccess: invalidate,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const scheduled = data.habits.items.filter((i) => i.scheduledToday);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Repeat className="size-4 text-primary" aria-hidden /> Habits today
        </CardTitle>
        <CardDescription>
          <Private>{data.habits.completed}</Private> of <Private>{data.habits.scheduled}</Private> done
          {data.habits.atRisk.length ? ` · ${data.habits.atRisk.length} streak at risk` : ""}
        </CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/habits">Habits</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {scheduled.length === 0 ? (
          <EmptyState icon={Repeat} title="No habits scheduled today" action={<Button asChild size="sm" variant="outline"><Link href="/habits">Create a habit</Link></Button>} />
        ) : (
          <ul className="space-y-1">
            {scheduled.map((habit) => (
              <li key={habit.habitId} className="flex items-center gap-3 rounded-md px-1 py-1.5">
                <Checkbox
                  checked={habit.done}
                  aria-label={`${habit.done ? "Undo" : "Complete"} ${habit.name}`}
                  disabled={toggle.isPending}
                  onCheckedChange={() => toggle.mutate({ habitId: habit.habitId, done: habit.done })}
                />
                <span className={`flex-1 truncate text-sm ${habit.done ? "text-muted-foreground line-through" : ""}`}>
                  {habit.name}
                </span>
                {habit.measure !== "check" ? (
                  <span className="tabular text-xs text-muted-foreground">
                    <Private>{habit.valueToday}</Private>/{habit.targetValue} {habit.unit ?? ""}
                  </span>
                ) : null}
                {habit.currentStreak > 0 ? (
                  <span className="flex items-center gap-0.5 text-xs text-amber-600 dark:text-amber-400" title="Current streak">
                    <Flame className="size-3.5" aria-hidden />
                    <Private>{habit.currentStreak}</Private>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Learning({ data }: { data: Dashboard }) {
  const { learning } = data;
  const todayPct = learning.goalMinutes ? Math.min(100, (learning.todayMinutes / learning.goalMinutes) * 100) : 0;
  const weekPct = learning.weekGoalMinutes ? Math.min(100, (learning.weekMinutes / learning.weekGoalMinutes) * 100) : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BookOpen className="size-4 text-primary" aria-hidden /> Learning
        </CardTitle>
        <CardDescription>Daily goal {formatMinutes(learning.goalMinutes)}</CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/work">Log time</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span>Today</span>
            <span className="tabular text-muted-foreground">
              <Private>{formatMinutes(learning.todayMinutes)}</Private> / {formatMinutes(learning.goalMinutes)}
            </span>
          </div>
          <Progress value={todayPct} aria-label="Today's learning progress" />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span>This week</span>
            <span className="tabular text-muted-foreground">
              <Private>{formatMinutes(learning.weekMinutes)}</Private> / {formatMinutes(learning.weekGoalMinutes)}
            </span>
          </div>
          <Progress value={weekPct} aria-label="This week's learning progress" />
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {learning.goalStreak > 0 ? (
            <Badge variant="secondary">
              <Flame className="size-3" aria-hidden /> <Private>{learning.goalStreak}</Private>-day goal streak
            </Badge>
          ) : null}
          {learning.bySkill.map((s) => (
            <Badge key={s.skillName} variant="outline">
              {s.skillName} · <Private>{formatMinutes(s.minutes)}</Private>
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Practice({ data }: { data: Dashboard }) {
  const { problems } = data;
  const stats = [
    { label: "Due for review", value: problems.dueForReview },
    { label: "Solved this week", value: problems.solvedThisWeek },
    { label: "Solved in total", value: problems.totalSolved },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="size-4 text-primary" aria-hidden /> DSA practice
        </CardTitle>
        <CardDescription>Spaced review keeps solutions fresh.</CardDescription>
        <CardAction>
          <Button asChild variant="ghost" size="sm">
            <Link href="/work?tab=practice">Practice</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-3 gap-2 text-center">
          {stats.map((s) => (
            <div key={s.label} className="rounded-md bg-muted/50 p-3">
              <dd className="tabular text-2xl font-semibold">
                <Private>{s.value}</Private>
              </dd>
              <dt className="text-xs text-muted-foreground">{s.label}</dt>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function TodayContent() {
  const me = useMe();
  const dashboard = useQuery({
    queryKey: qk.dashboard,
    queryFn: () => unwrap(api.GET("/api/v1/dashboard")),
  });
  const name = me.data?.user.displayName.split(" ")[0] ?? "";

  return (
    <>
      <PageHeader
        title={`${greeting(new Date().getHours())}${name ? `, ${name}` : ""}`}
        description={dashboard.data ? dayLabel(dashboard.data.date) : undefined}
      />
      {dashboard.isPending ? (
        <LoadingRows rows={6} />
      ) : dashboard.isError ? (
        <ErrorState error={dashboard.error} onRetry={() => dashboard.refetch()} />
      ) : (
        <div className="space-y-4">
          <Card className="border-primary/30 bg-primary/5">
            <CardContent className="flex flex-wrap items-center gap-4">
              <Sparkles className="size-5 text-primary" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-muted-foreground">Daily brief</p>
                <p className="text-lg font-medium">
                  <Private>{dashboard.data.brief.headline}</Private>
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link href="/library?capture=1">Save to library</Link>
                </Button>
                <Button asChild>
                  <Link href="/chief?ask=focus">Plan my day</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
          <div className="grid gap-4 md:grid-cols-2">
            <PriorityTasks data={dashboard.data} />
            <HabitsToday data={dashboard.data} />
            <Learning data={dashboard.data} />
            <Practice data={dashboard.data} />
          </div>
        </div>
      )}
    </>
  );
}

// The greeting depends on the current hour, so it is computed on each visit, not at build time.
export default function TodayPage() {
  return (
    <Suspense fallback={<LoadingRows rows={5} />}>
      <TodayContent />
    </Suspense>
  );
}
