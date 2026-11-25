"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Flame, Pause, Play, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage, unwrap } from "@/lib/api";
import { dayLabel, formatMinutes, parseDay } from "@/lib/format";
import { qk } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { useSkills } from "./use-skills";

const NO_SKILL = "none";

function useInvalidateLearning() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: qk.professional });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
  };
}

function SkillSelect({ value, onChange, id }: { value: string; onChange: (v: string) => void; id?: string }) {
  const skills = useSkills();
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className="w-full" aria-label="Skill">
        <SelectValue placeholder="Skill" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NO_SKILL}>No skill</SelectItem>
        {(skills.data ?? []).map((s) => (
          <SelectItem key={s.id} value={s.id}>
            {s.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function FocusTimer() {
  const invalidate = useInvalidateLearning();
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [topic, setTopic] = useState("");
  const [skill, setSkill] = useState(NO_SKILL);

  useEffect(() => {
    if (startedAt === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);

  const save = useMutation({
    mutationFn: (minutes: number) =>
      unwrap(
        api.POST("/api/v1/professional/learning-sessions", {
          body: {
            durationMin: minutes,
            topic: topic.trim() || "Focus session",
            skillId: skill === NO_SKILL ? null : skill,
            startedAt: startedAt ? new Date(startedAt).toISOString() : null,
          },
        }),
      ),
    onSuccess: (session) => {
      toast.success(`Logged ${formatMinutes(session.durationMin)} of ${session.topic}`);
      setStartedAt(null);
      setTopic("");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const elapsedMs = startedAt ? now - startedAt : 0;
  const mm = String(Math.floor(elapsedMs / 60000)).padStart(2, "0");
  const ss = String(Math.floor((elapsedMs % 60000) / 1000)).padStart(2, "0");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Focus timer</CardTitle>
        <CardDescription>Start when you sit down; stopping logs the session.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="tabular text-center text-4xl font-semibold" aria-live="polite" aria-label={`Elapsed ${mm} minutes ${ss} seconds`}>
          {mm}:{ss}
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input aria-label="What are you studying?" placeholder="What are you studying?" value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)} />
          <SkillSelect value={skill} onChange={setSkill} />
        </div>
        {startedAt === null ? (
          <Button className="w-full" onClick={() => { setNow(Date.now()); setStartedAt(Date.now()); }}>
            <Play className="size-4" aria-hidden /> Start
          </Button>
        ) : (
          <div className="flex gap-2">
            <Button
              className="flex-1"
              disabled={save.isPending}
              onClick={() => save.mutate(Math.min(1440, Math.max(1, Math.round(elapsedMs / 60000))))}
            >
              <Pause className="size-4" aria-hidden /> Stop & log
            </Button>
            <Button variant="outline" onClick={() => setStartedAt(null)}>
              Discard
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ManualLog() {
  const invalidate = useInvalidateLearning();
  const [minutes, setMinutes] = useState("30");
  const [topic, setTopic] = useState("");
  const [skill, setSkill] = useState(NO_SKILL);
  const [date, setDate] = useState(() => new Date().toLocaleDateString("en-CA"));

  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/professional/learning-sessions", {
          body: {
            durationMin: Number(minutes),
            topic: topic.trim(),
            skillId: skill === NO_SKILL ? null : skill,
            localDate: date,
          },
        }),
      ),
    onSuccess: () => {
      toast.success("Session logged");
      setTopic("");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Log time</CardTitle>
        <CardDescription>Add a session you did earlier.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="log-topic">Topic</Label>
            <Input id="log-topic" required maxLength={200} value={topic} placeholder="e.g. Graphs: Dijkstra" onChange={(e) => setTopic(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="log-minutes">Minutes</Label>
            <Input id="log-minutes" type="number" min={1} max={1440} required value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="log-date">Date</Label>
            <Input id="log-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="log-skill">Skill</Label>
            <SkillSelect id="log-skill" value={skill} onChange={setSkill} />
          </div>
          <Button type="submit" className="sm:col-span-2" disabled={save.isPending || !topic.trim()}>
            {save.isPending ? "Saving…" : "Log session"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function WeekChart() {
  const summary = useQuery({
    queryKey: [...qk.professional, "summary"],
    queryFn: () => unwrap(api.GET("/api/v1/professional/learning-sessions/summary")),
  });
  if (summary.isPending) return <LoadingRows rows={4} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const data = summary.data;
  const scale = Math.max(data.goalMinutesPerDay, ...data.daily.map((d) => d.minutes), 1);
  const goalPct = (data.goalMinutesPerDay / scale) * 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle>This week</CardTitle>
        <CardDescription>
          <Private>{formatMinutes(data.totalMinutes)}</Private> total · goal met on{" "}
          <Private>{data.goalDaysMet}</Private> of {data.daily.length} days
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="relative h-40" role="img" aria-label="Minutes learned per day this week">
          {data.goalMinutesPerDay > 0 ? (
            <div
              className="absolute inset-x-0 border-t border-dashed border-primary/60"
              style={{ bottom: `${goalPct}%` }}
              aria-hidden
            >
              <span className="absolute -top-4 right-0 text-[10px] text-primary">goal</span>
            </div>
          ) : null}
          <ol className="flex h-full items-end gap-2">
            {data.daily.map((day) => (
              <li key={day.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                <div
                  className={cn(
                    "w-full rounded-t-sm",
                    day.minutes >= data.goalMinutesPerDay && data.goalMinutesPerDay > 0 ? "bg-primary" : "bg-primary/40",
                  )}
                  style={{ height: `${Math.max(2, (day.minutes / scale) * 100)}%` }}
                  title={`${dayLabel(day.date)}: ${formatMinutes(day.minutes)}`}
                />
                <span className="text-[11px] text-muted-foreground">
                  {parseDay(day.date).toLocaleDateString(undefined, { weekday: "narrow" })}
                </span>
              </li>
            ))}
          </ol>
        </div>
        <table className="sr-only">
          <caption>Minutes per day</caption>
          <tbody>
            {data.daily.map((d) => (
              <tr key={d.date}>
                <th scope="row">{dayLabel(d.date)}</th>
                <td>{d.minutes}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex flex-wrap gap-2">
          {data.currentGoalStreak > 0 ? (
            <Badge variant="secondary">
              <Flame className="size-3" aria-hidden /> <Private>{data.currentGoalStreak}</Private>-day goal streak
            </Badge>
          ) : null}
          {data.bySkill.map((s) => (
            <Badge key={s.skillName} variant="outline">
              {s.skillName} · <Private>{formatMinutes(s.minutes)}</Private>
            </Badge>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function RecentSessions() {
  const invalidate = useInvalidateLearning();
  const skills = useSkills();
  const sessions = useQuery({
    queryKey: [...qk.professional, "sessions"],
    queryFn: () => unwrap(api.GET("/api/v1/professional/learning-sessions", { params: { query: { limit: 20 } } })),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/professional/learning-sessions/{session_id}", { params: { path: { session_id: id } } })),
    onSuccess: invalidate,
  });
  const skillName = (id: string | null | undefined) => skills.data?.find((s) => s.id === id)?.name;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
      </CardHeader>
      <CardContent>
        {sessions.isPending ? (
          <LoadingRows />
        ) : sessions.isError ? (
          <ErrorState error={sessions.error} onRetry={() => sessions.refetch()} />
        ) : sessions.data.items.length === 0 ? (
          <EmptyState icon={BookOpen} title="No sessions yet" description="Start the timer or log time to see it here." />
        ) : (
          <ul className="divide-y text-sm">
            {sessions.data.items.map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-2">
                <span className="w-24 shrink-0 text-xs text-muted-foreground">{dayLabel(s.localDate)}</span>
                <span className="min-w-0 flex-1 truncate">{s.topic}</span>
                {skillName(s.skillId) ? <Badge variant="outline">{skillName(s.skillId)}</Badge> : null}
                <span className="tabular w-14 text-right">
                  <Private>{formatMinutes(s.durationMin)}</Private>
                </span>
                <Button variant="ghost" size="icon" aria-label={`Delete session ${s.topic}`} onClick={() => remove.mutate(s.id)}>
                  <Trash2 className="size-4" aria-hidden />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function LearningTab() {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <FocusTimer />
        <ManualLog />
      </div>
      <div className="space-y-4">
        <WeekChart />
        <RecentSessions />
      </div>
    </div>
  );
}
