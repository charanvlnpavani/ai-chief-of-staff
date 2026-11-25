"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, MessageSquarePlus, Send, ShieldCheck, Sparkles, Trash2, Wrench } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Private } from "@/components/privacy";
import { ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { qk } from "@/lib/queries";
import { readSse } from "@/lib/sse";
import { cn } from "@/lib/utils";

type DisplayMessage = Schemas["DisplayMessage"];

const SUGGESTIONS = [
  "What should I focus on today?",
  "How is my learning going this week?",
  "Which habits am I at risk of missing?",
  "Which DSA problems should I review next?",
];
const TOOL_LABELS: Record<string, string> = {
  get_daily_snapshot: "today's overview",
  list_tasks: "your tasks",
  get_task_counts: "task counts",
  get_habits_today: "today's habits",
  get_habit_stats: "habit streaks",
  get_learning_summary: "learning time",
  list_practice_problems: "your problem log",
  get_review_queue: "your review queue",
  get_skill_matrix: "your skills",
};

interface LiveTurn {
  user: string;
  text: string;
  tools: { name: string; status: string }[];
}

function ConsentCard() {
  const queryClient = useQueryClient();
  const grant = useMutation({
    mutationFn: () => unwrap(api.PUT("/api/v1/users/me/consents/{category}", { params: { path: { category: "ai_processing" } }, body: { granted: true } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: qk.ai }),
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-5 text-primary" aria-hidden /> Before you start
        </CardTitle>
        <CardDescription>The Chief of Staff uses Claude, an AI model made by Anthropic.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>When you ask a question, Personal OS sends Anthropic:</p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>your message, the date and your time zone;</li>
          <li>only the records Claude looks up through read-only tools: tasks, habits, goals (titles, targets, progress), learning roadmaps, learning sessions, practice problems and skills.</li>
          <li>when you plan a roadmap for a new subject: the subject you typed and how much time you want to spend.</li>
        </ul>
        <p>It never sends your email address, passwords or session tokens, and it cannot change, delete or send anything.</p>
        <p className="text-muted-foreground">
          Conversations are stored encrypted in your own database and deleted after 90 days. You can withdraw consent in Settings at any time.
        </p>
      </CardContent>
      <CardFooter>
        <Button onClick={() => grant.mutate()} disabled={grant.isPending}>
          I agree, turn on the Chief of Staff
        </Button>
      </CardFooter>
    </Card>
  );
}

function Message({ role, text, tools }: { role: "user" | "assistant"; text: string; tools?: { name: string; ok?: boolean; status?: string }[] }) {
  return (
    <li className={cn("flex flex-col gap-1", role === "user" ? "items-end" : "items-start")}>
      {tools && tools.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {tools.map((t, i) => (
            <Badge key={`${t.name}-${i}`} variant="outline" className="gap-1 text-xs font-normal">
              {t.status === "running" ? <Loader2 className="size-3 animate-spin" aria-hidden /> : <Wrench className="size-3" aria-hidden />}
              {t.status === "running" ? "Looking at " : "Checked "}
              {TOOL_LABELS[t.name] ?? t.name}
            </Badge>
          ))}
        </div>
      ) : null}
      {text ? (
        <div
          className={cn(
            "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
          )}
        >
          {text}
        </div>
      ) : null}
    </li>
  );
}

export function ChiefOfStaff() {
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState(params.get("ask") === "focus" ? SUGGESTIONS[0] : "");
  const [live, setLive] = useState<LiveTurn | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const status = useQuery({ queryKey: [...qk.ai, "status"], queryFn: () => unwrap(api.GET("/api/v1/ai/status")) });
  const conversations = useQuery({
    queryKey: [...qk.ai, "conversations"],
    queryFn: () => unwrap(api.GET("/api/v1/ai/conversations")),
  });
  const conversationId = selected ?? conversations.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: [...qk.ai, "conversation", conversationId],
    queryFn: () =>
      unwrap(api.GET("/api/v1/ai/conversations/{conversation_id}", { params: { path: { conversation_id: conversationId ?? "" } } })),
    enabled: conversationId !== null,
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [detail.data, live?.text, live?.tools.length]);

  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/ai/conversations/{conversation_id}", { params: { path: { conversation_id: id } } })),
    onSuccess: () => {
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: qk.ai });
    },
  });

  async function send(text: string) {
    const content = text.trim();
    if (!content || live) return;
    setDraft("");
    setLive({ user: content, text: "", tools: [] });
    try {
      let id = conversationId;
      if (id === null) {
        const created = await unwrap(api.POST("/api/v1/ai/conversations", { body: {} }));
        id = created.id;
        setSelected(id);
      }
      const response = await fetch(`/api/v1/ai/conversations/${id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
        credentials: "same-origin",
      });
      if (!response.ok || !response.body) {
        const problem = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
        throw new ApiError(response.status, problem.code ?? "http_error", problem.detail ?? "The Chief of Staff could not answer.");
      }
      for await (const event of readSse(response.body)) {
        const data = event.data as Record<string, unknown>;
        if (event.event === "text") {
          setLive((turn) => (turn ? { ...turn, text: turn.text + String(data.delta ?? "") } : turn));
        } else if (event.event === "tool") {
          const name = String(data.name);
          const toolStatus = String(data.status);
          setLive((turn) => {
            if (!turn) return turn;
            const others = turn.tools.filter((t) => !(t.name === name && t.status === "running"));
            return { ...turn, tools: [...others, { name, status: toolStatus }] };
          });
        } else if (event.event === "error") {
          toast.error(String(data.message ?? "The Chief of Staff stopped early."));
        }
      }
    } catch (error) {
      toast.error(errorMessage(error));
      setDraft(content);
    } finally {
      await queryClient.invalidateQueries({ queryKey: qk.ai });
      setLive(null);
    }
  }

  if (status.isPending) return <LoadingRows rows={4} />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;

  const ai = status.data;
  const messages: DisplayMessage[] = detail.data?.messages ?? [];

  return (
    <>
      <PageHeader
        title="Chief of Staff"
        description="Ask about your day, progress and priorities. It can read and suggest; it never changes anything."
        actions={
          <>
            <Badge variant="outline" className="h-8 gap-1 px-3 font-normal" title="Spend this month vs your budget">
              <Private>${ai.monthToDateUsd.toFixed(2)}</Private> of ${ai.monthlyBudgetUsd.toFixed(0)} this month
            </Badge>
            <Button variant="outline" onClick={() => setSelected(null)} disabled={live !== null}>
              <MessageSquarePlus className="size-4" aria-hidden /> New chat
            </Button>
          </>
        }
      />

      {!ai.enabled ? (
        <Alert className="mb-4">
          <KeyRound className="size-4" aria-hidden />
          <AlertTitle>Add your Anthropic API key to turn this on</AlertTitle>
          <AlertDescription>
            Put ANTHROPIC_API_KEY in backend/.env and restart the API. Set a monthly spend limit in the Claude Console as well;
            your in-app budget is ${ai.monthlyBudgetUsd.toFixed(0)}/month. Model: {ai.model}.
          </AlertDescription>
        </Alert>
      ) : null}

      {!ai.consentGranted ? (
        <ConsentCard />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[14rem_1fr]">
          <nav aria-label="Conversations" className="hidden lg:block">
            <ul className="space-y-1">
              {(conversations.data ?? []).map((c) => (
                <li key={c.id} className="group flex items-center">
                  <button
                    type="button"
                    onClick={() => setSelected(c.id)}
                    aria-current={c.id === conversationId ? "true" : undefined}
                    className={cn(
                      "flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                      c.id === conversationId && "bg-muted font-medium",
                    )}
                  >
                    {c.title ?? "New conversation"}
                  </button>
                  <Button variant="ghost" size="icon" className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100" aria-label={`Delete conversation ${c.title ?? ""}`} onClick={() => remove.mutate(c.id)}>
                    <Trash2 className="size-3.5" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          </nav>

          <Card className="flex min-h-[60vh] flex-col">
            <CardContent className="flex-1 overflow-y-auto">
              {messages.length === 0 && !live ? (
                <div className="flex h-full flex-col items-center justify-center gap-4 py-10 text-center">
                  <Sparkles className="size-8 text-primary" aria-hidden />
                  <p className="max-w-md text-muted-foreground">
                    I can look at your tasks, habits, learning time and practice log, and suggest what to do next.
                  </p>
                  <div className="flex max-w-lg flex-wrap justify-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <Button key={s} variant="outline" size="sm" onClick={() => setDraft(s)}>
                        {s}
                      </Button>
                    ))}
                  </div>
                </div>
              ) : (
                <ol className="space-y-4" aria-live="polite">
                  {messages.map((m) => (
                    <Message key={m.id} role={m.role} text={m.text} tools={m.toolCalls} />
                  ))}
                  {live ? (
                    <>
                      <Message role="user" text={live.user} />
                      <Message role="assistant" text={live.text || (live.tools.length ? "" : "Thinking…")} tools={live.tools} />
                    </>
                  ) : null}
                </ol>
              )}
              <div ref={endRef} />
            </CardContent>
            <CardFooter className="border-t pt-4">
              <form
                className="flex w-full items-end gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  void send(draft);
                }}
              >
                <label htmlFor="chief-input" className="sr-only">
                  Message the Chief of Staff
                </label>
                <Textarea
                  id="chief-input"
                  rows={2}
                  maxLength={4000}
                  value={draft}
                  placeholder={ai.enabled ? "Ask anything about your day…" : "Add an API key to start"}
                  disabled={!ai.enabled || live !== null}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(draft);
                    }
                  }}
                  className="min-h-12 flex-1 resize-none"
                />
                <Button type="submit" size="icon" aria-label="Send" disabled={!ai.enabled || live !== null || !draft.trim()}>
                  {live ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
                </Button>
              </form>
            </CardFooter>
          </Card>
        </div>
      )}
    </>
  );
}
