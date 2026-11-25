"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, ExternalLink, RotateCcw, Target, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
import { EmptyState, ErrorState, LoadingRows } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { dayLabel } from "@/lib/format";
import { qk } from "@/lib/queries";

type Problem = Schemas["ProblemOut"];
type Outcome = "solved" | "partial" | "failed";
type Status = "todo" | "attempted" | "solved" | "revisit";
type Difficulty = "easy" | "medium" | "hard";
type Platform = "leetcode" | "gfg" | "codeforces" | "hackerrank" | "codechef" | "other";

const DIFFICULTY_STYLE: Record<string, string> = {
  easy: "text-emerald-600 dark:text-emerald-400",
  medium: "text-amber-600 dark:text-amber-400",
  hard: "text-destructive",
};

function slugify(title: string): string {
  return title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
}

function useInvalidatePractice() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: qk.professional });
    void queryClient.invalidateQueries({ queryKey: qk.dashboard });
  };
}

function useAttempt() {
  const invalidate = useInvalidatePractice();
  return useMutation({
    mutationFn: ({ problem, outcome }: { problem: Problem; outcome: Outcome }) =>
      unwrap(
        api.POST("/api/v1/professional/problems/{problem_id}/attempts", {
          params: { path: { problem_id: problem.id } },
          body: { outcome },
        }),
      ),
    onSuccess: (problem) => {
      toast.success(
        problem.nextReviewOn ? `Next review ${dayLabel(problem.nextReviewOn)}` : "Attempt logged",
      );
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
}

function AttemptButtons({ problem }: { problem: Problem }) {
  const attempt = useAttempt();
  return (
    <div className="flex gap-1">
      <Button size="xs" variant="outline" disabled={attempt.isPending} onClick={() => attempt.mutate({ problem, outcome: "solved" })}>
        <CheckCircle2 className="size-3.5 text-emerald-600" aria-hidden /> Solved
      </Button>
      <Button size="xs" variant="outline" disabled={attempt.isPending} onClick={() => attempt.mutate({ problem, outcome: "partial" })}>
        <CircleDashed className="size-3.5" aria-hidden /> Partial
      </Button>
      <Button size="xs" variant="outline" disabled={attempt.isPending} onClick={() => attempt.mutate({ problem, outcome: "failed" })}>
        <XCircle className="size-3.5 text-destructive" aria-hidden /> Failed
      </Button>
    </div>
  );
}

function AddProblem() {
  const invalidate = useInvalidatePractice();
  const [title, setTitle] = useState("");
  const [platform, setPlatform] = useState<Platform>("leetcode");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [topics, setTopics] = useState("");
  const [url, setUrl] = useState("");

  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/professional/problems", {
          body: {
            title: title.trim(),
            slug: slugify(title),
            platform,
            difficulty,
            url: url.trim() || null,
            topics: topics.split(",").map((t) => t.trim()).filter(Boolean),
          },
        }),
      ),
    onSuccess: () => {
      toast.success("Problem added");
      setTitle("");
      setTopics("");
      setUrl("");
      invalidate();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add a problem</CardTitle>
        <CardDescription>Entered by you; nothing is scraped from coding sites.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="problem-title">Title</Label>
            <Input id="problem-title" required maxLength={200} value={title} placeholder="e.g. LRU Cache" onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Platform</Label>
            <Select value={platform} onValueChange={(v) => setPlatform(v as Platform)}>
              <SelectTrigger className="w-full" aria-label="Platform"><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["leetcode", "gfg", "codeforces", "hackerrank", "codechef", "other"] as const).map((p) => (
                  <SelectItem key={p} value={p}>{p === "gfg" ? "GeeksforGeeks" : p[0].toUpperCase() + p.slice(1)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Difficulty</Label>
            <Select value={difficulty} onValueChange={(v) => setDifficulty(v as Difficulty)}>
              <SelectTrigger className="w-full" aria-label="Difficulty"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="easy">Easy</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="hard">Hard</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="problem-topics">Topics</Label>
            <Input id="problem-topics" value={topics} placeholder="graph, bfs" onChange={(e) => setTopics(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="problem-url">Link</Label>
            <Input id="problem-url" type="url" value={url} placeholder="https://…" onChange={(e) => setUrl(e.target.value)} />
          </div>
          <Button type="submit" className="sm:col-span-2" disabled={create.isPending || !slugify(title)}>
            {create.isPending ? "Adding…" : "Add to log"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ReviewQueue() {
  const queue = useQuery({
    queryKey: [...qk.professional, "review-queue"],
    queryFn: () => unwrap(api.GET("/api/v1/professional/problems/review-queue")),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RotateCcw className="size-4 text-primary" aria-hidden /> Due for review
        </CardTitle>
        <CardDescription>Re-solve these from memory. Solving pushes the next review further out.</CardDescription>
      </CardHeader>
      <CardContent>
        {queue.isPending ? (
          <LoadingRows />
        ) : queue.isError ? (
          <ErrorState error={queue.error} onRetry={() => queue.refetch()} />
        ) : queue.data.length === 0 ? (
          <EmptyState icon={RotateCcw} title="Nothing due" description="Problems you solve come back here on a schedule." />
        ) : (
          <ul className="divide-y">
            {queue.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-medium">{p.title}</span>
                <span className={`text-xs ${DIFFICULTY_STYLE[p.difficulty]}`}>{p.difficulty}</span>
                <AttemptButtons problem={p} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Stats() {
  const stats = useQuery({
    queryKey: [...qk.professional, "problem-stats"],
    queryFn: () => unwrap(api.GET("/api/v1/professional/problems/stats")),
  });
  if (stats.isPending) return <LoadingRows rows={2} />;
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => stats.refetch()} />;
  const s = stats.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Progress</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid grid-cols-3 gap-2 text-center">
          {(["easy", "medium", "hard"] as const).map((d) => (
            <div key={d} className="rounded-md bg-muted/50 p-2">
              <dd className={`tabular text-xl font-semibold ${DIFFICULTY_STYLE[d]}`}>
                <Private>{s.solvedByDifficulty[d] ?? 0}</Private>
              </dd>
              <dt className="text-xs capitalize text-muted-foreground">{d} solved</dt>
            </div>
          ))}
        </dl>
        <p className="text-sm text-muted-foreground">
          <Private>{s.total}</Private> in your log · <Private>{s.solvedThisWeek}</Private> newly solved this week
        </p>
        {s.topTopics.length ? (
          <div className="flex flex-wrap gap-1">
            {s.topTopics.map((t) => (
              <Badge key={t.topic} variant="secondary">
                {t.topic} · {t.count}
              </Badge>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ProblemLog() {
  const invalidate = useInvalidatePractice();
  const [status, setStatus] = useState<Status | "all">("all");
  const problems = useQuery({
    queryKey: [...qk.professional, "problems", status],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/professional/problems", {
          params: { query: { status: status === "all" ? undefined : status, limit: 100 } },
        }),
      ),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/professional/problems/{problem_id}", { params: { path: { problem_id: id } } })),
    onSuccess: invalidate,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Problem log</CardTitle>
        <CardAction>
          <Select value={status} onValueChange={(v) => setStatus(v as Status | "all")}>
            <SelectTrigger className="w-36" aria-label="Filter by status"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="todo">To do</SelectItem>
              <SelectItem value="attempted">Attempted</SelectItem>
              <SelectItem value="solved">Solved</SelectItem>
              <SelectItem value="revisit">Revisit</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent>
        {problems.isPending ? (
          <LoadingRows />
        ) : problems.isError ? (
          <ErrorState error={problems.error} onRetry={() => problems.refetch()} />
        ) : problems.data.items.length === 0 ? (
          <EmptyState icon={Target} title="No problems yet" description="Add the problems you work on to track attempts and reviews." />
        ) : (
          <ul className="divide-y">
            {problems.data.items.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1 truncate font-medium">
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:underline">
                        {p.title} <ExternalLink className="size-3" aria-label="opens in a new tab" />
                      </a>
                    ) : (
                      p.title
                    )}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <span className={DIFFICULTY_STYLE[p.difficulty]}>{p.difficulty}</span> · {p.attempts} attempt
                    {p.attempts === 1 ? "" : "s"}
                    {p.nextReviewOn ? ` · review ${dayLabel(p.nextReviewOn)}` : ""}
                    {p.topics.length ? ` · ${p.topics.join(", ")}` : ""}
                  </p>
                </div>
                <Badge variant={p.status === "solved" ? "default" : "secondary"}>{p.status}</Badge>
                <AttemptButtons problem={p} />
                <Button variant="ghost" size="icon" aria-label={`Delete ${p.title}`} onClick={() => remove.mutate(p.id)}>
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

export function PracticeTab() {
  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_3fr]">
      <div className="space-y-4">
        <AddProblem />
        <Stats />
      </div>
      <div className="space-y-4">
        <ReviewQueue />
        <ProblemLog />
      </div>
    </div>
  );
}
