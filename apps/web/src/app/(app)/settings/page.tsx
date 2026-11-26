"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { usePrivacy } from "@/components/privacy";
import { ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { qk, useMe } from "@/lib/queries";

type Me = Schemas["MeOut"];
type ConsentCategory = Schemas["ConsentOut"]["category"];

const CONSENT_INFO: Record<ConsentCategory, { title: string; description: string; available: boolean }> = {
  ai_processing: {
    title: "Chief of Staff (AI)",
    description: "Lets your connected AI provider read your tasks, habits, goals, roadmaps, learning and practice records when you ask it something, and plan roadmaps for subjects you type.",
    available: true,
  },
  ai_health: { title: "AI access to health data", description: "Arrives with the Health manager (Release 2).", available: false },
  ai_finance: { title: "AI access to finance data", description: "Arrives with the Finance manager (Release 2).", available: false },
  ai_email_content: { title: "AI reading of email content", description: "Arrives with Gmail ingestion (Release 4).", available: false },
};

function timeZones(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [];
  }
}

function ProfileCard({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(me.user.displayName);
  const [tz, setTz] = useState(me.user.timezone);
  const [currency, setCurrency] = useState(me.user.currency);
  const save = useMutation({
    mutationFn: () => unwrap(api.PATCH("/api/v1/users/me", { body: { displayName: name, timezone: tz, currency: currency.toUpperCase() } })),
    onSuccess: () => {
      toast.success("Profile saved");
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your time zone decides what &ldquo;today&rdquo; means everywhere in the app.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="space-y-1.5">
            <Label htmlFor="profile-name">Name</Label>
            <Input id="profile-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-tz">Time zone</Label>
            <Input id="profile-tz" list="time-zones" required value={tz} onChange={(e) => setTz(e.target.value)} />
            <datalist id="time-zones">
              {timeZones().map((zone) => (
                <option key={zone} value={zone} />
              ))}
            </datalist>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-currency">Currency</Label>
            <Input id="profile-currency" required maxLength={3} pattern="[A-Za-z]{3}" value={currency} onChange={(e) => setCurrency(e.target.value)} />
          </div>
          <Button type="submit" className="sm:col-span-3 sm:justify-self-start" disabled={save.isPending}>
            Save profile
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function PreferencesCard({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const { setHidden } = usePrivacy();
  const [goal, setGoal] = useState(String(me.preferences.dailyLearningGoalMinutes ?? 120));
  const [budget, setBudget] = useState(String(me.preferences.ai?.monthlyBudgetUsd ?? 25));
  const [privacyDefault, setPrivacyDefault] = useState(me.preferences.privacyModeDefault ?? false);

  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/users/me/settings", {
          body: {
            dailyLearningGoalMinutes: Number(goal),
            privacyModeDefault: privacyDefault,
            ai: { monthlyBudgetUsd: Number(budget) },
          },
        }),
      ),
    onSuccess: () => {
      toast.success("Preferences saved");
      if (privacyDefault) setHidden(true);
      void queryClient.invalidateQueries();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Preferences</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <div className="space-y-1.5">
            <Label htmlFor="pref-goal">Daily learning goal (minutes)</Label>
            <Input id="pref-goal" type="number" min={0} max={1440} value={goal} onChange={(e) => setGoal(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pref-budget">AI budget per month (USD)</Label>
            <Input id="pref-budget" type="number" min={0} max={1000} step="1" value={budget} onChange={(e) => setBudget(e.target.value)} />
            <p className="text-xs text-muted-foreground">Requests stop once this month&apos;s Claude spend reaches it.</p>
          </div>
          <div className="flex items-center gap-3 sm:col-span-2">
            <Switch id="pref-privacy" checked={privacyDefault} onCheckedChange={setPrivacyDefault} />
            <Label htmlFor="pref-privacy">Start with privacy mode on (numbers hidden until you reveal them)</Label>
          </div>
          <Button type="submit" className="sm:justify-self-start" disabled={save.isPending}>
            Save preferences
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

type Provider = Schemas["ProviderOut"];
type Connection = Schemas["ConnectionOut"];

function ModelPicker({ connection, onDone }: { connection: Connection; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [typed, setTyped] = useState(connection.model ?? "");
  const models = useQuery({
    queryKey: [...qk.ai, "models", connection.provider],
    queryFn: () =>
      unwrap(api.GET("/api/v1/ai/connections/{provider}/models", { params: { path: { provider: connection.provider } } })),
  });
  const choose = useMutation({
    mutationFn: (model: string) =>
      unwrap(
        api.PATCH("/api/v1/ai/connections/{provider}", {
          params: { path: { provider: connection.provider } },
          body: { model, active: true },
        }),
      ),
    onSuccess: (next) => {
      queryClient.setQueryData([...qk.ai, "connections"], next);
      void queryClient.invalidateQueries({ queryKey: qk.ai });
      toast.success("Model saved. AI features now use it.");
      onDone();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  const list = models.data ?? [];
  return (
    <div className="space-y-2 rounded-md border p-3">
      {models.isPending ? (
        <LoadingRows rows={1} />
      ) : models.isError ? (
        <ErrorState error={models.error} onRetry={() => models.refetch()} />
      ) : list.length > 0 ? (
        <div className="space-y-1.5">
          <Label>Model ({list.length} available)</Label>
          <Select value={connection.model ?? undefined} onValueChange={(model) => choose.mutate(model)}>
            <SelectTrigger className="w-full" aria-label="Model">
              <SelectValue placeholder="Choose a model" />
            </SelectTrigger>
            <SelectContent className="max-h-72">
              {[...list]
                .sort((a, b) => Number(b.free) - Number(a.free) || a.id.localeCompare(b.id))
                .map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.id}
                    {m.free ? " · free" : ""}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">This provider did not list its models. Type the model name.</p>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (typed.trim()) choose.mutate(typed.trim());
        }}
      >
        <Input aria-label="Model name" placeholder="Or type a model name" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <Button type="submit" variant="outline" disabled={!typed.trim() || choose.isPending}>
          Use
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">The Chief of Staff needs a model that supports tool (function) calling.</p>
    </div>
  );
}

function ConnectionRow({ connection, isOnly }: { connection: Connection; isOnly: boolean }) {
  const queryClient = useQueryClient();
  const [picking, setPicking] = useState(!connection.model);
  const store = (next: Schemas["ConnectionsOut"]) => {
    queryClient.setQueryData([...qk.ai, "connections"], next);
    void queryClient.invalidateQueries({ queryKey: qk.ai });
  };
  const activate = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/ai/connections/{provider}", { params: { path: { provider: connection.provider } }, body: { active: true } }),
      ),
    onSuccess: store,
    onError: (error) => toast.error(errorMessage(error)),
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/ai/connections/{provider}", { params: { path: { provider: connection.provider } } })),
    onSuccess: (next) => {
      store(next);
      toast.success(`Disconnected ${connection.providerName}`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <li className="space-y-2 py-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{connection.providerName}</span>
        {connection.active ? <Badge>In use</Badge> : null}
        {connection.free ? <Badge variant="secondary">Free</Badge> : null}
        <span className="text-muted-foreground">
          {[connection.model ?? "no model chosen", connection.hint ? `key ${connection.hint}` : null, connection.baseUrl]
            .filter(Boolean)
            .join(" · ")}
        </span>
        <span className="ml-auto flex gap-1">
          {!connection.active && connection.model ? (
            <Button size="sm" variant="outline" disabled={activate.isPending} onClick={() => activate.mutate()}>
              Use this
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => setPicking(!picking)}>
            {picking ? "Close" : "Change model"}
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
            Disconnect
          </Button>
        </span>
      </div>
      {picking ? <ModelPicker connection={connection} onDone={() => setPicking(false)} /> : null}
      {isOnly && !connection.model ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">Choose a model to turn AI features on.</p>
      ) : null}
    </li>
  );
}

function ConnectProviderForm({ providers }: { providers: Provider[] }) {
  const queryClient = useQueryClient();
  const [providerId, setProviderId] = useState(providers[0]?.id ?? "anthropic");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const provider = providers.find((p) => p.id === providerId);
  const connect = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/ai/connections/{provider}", {
          params: { path: { provider: providerId } },
          body: { apiKey: apiKey.trim() || null, baseUrl: provider?.customUrl ? baseUrl.trim() || null : null },
        }),
      ),
    onSuccess: (next) => {
      queryClient.setQueryData([...qk.ai, "connections"], next);
      void queryClient.invalidateQueries({ queryKey: qk.ai });
      setApiKey("");
      toast.success(`${provider?.name ?? "Provider"} connected and checked.`);
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  if (!provider) return null;
  const canSubmit = provider.needsKey ? apiKey.trim() !== "" : true;
  return (
    <form
      className="space-y-3 rounded-lg border p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) connect.mutate();
      }}
    >
      <p className="text-sm font-medium">Connect a provider</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Provider</Label>
          <Select
            value={providerId}
            onValueChange={(id) => {
              setProviderId(id as typeof providerId);
              setBaseUrl("");
            }}
          >
            <SelectTrigger className="w-full" aria-label="Provider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {provider.needsKey || provider.id === "custom" ? (
          <div className="space-y-1.5">
            <Label htmlFor="provider-key">API key{provider.needsKey ? "" : " (if the endpoint needs one)"}</Label>
            <Input
              id="provider-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
              placeholder={provider.id === "anthropic" ? "sk-ant-..." : "Paste your key"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        ) : null}
        {provider.customUrl ? (
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="provider-url">Endpoint URL</Label>
            <Input
              id="provider-url"
              spellCheck={false}
              className="font-mono"
              placeholder={provider.defaultBaseUrl ?? "https://your-endpoint/v1"}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">
        {provider.freeNote ? `${provider.freeNote} ` : null}
        {provider.keyUrl ? (
          <>
            {provider.needsKey ? "Get a key at " : "Download at "}
            <a href={provider.keyUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2">
              {provider.keyUrl.replace("https://", "")}
            </a>
            .
          </>
        ) : null}
      </p>
      <Button type="submit" disabled={!canSubmit || connect.isPending}>
        {connect.isPending ? "Checking…" : `Connect ${provider.name}`}
      </Button>
    </form>
  );
}

function AiProviderCard() {
  const providers = useQuery({ queryKey: [...qk.ai, "providers"], queryFn: () => unwrap(api.GET("/api/v1/ai/providers")) });
  const status = useQuery({ queryKey: [...qk.ai, "connections"], queryFn: () => unwrap(api.GET("/api/v1/ai/connections")) });
  const s = status.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4 text-primary" aria-hidden /> AI provider
        </CardTitle>
        <CardDescription>
          Use Claude, ChatGPT models, Gemini, OpenRouter, Groq, a free local model with Ollama, or any OpenAI-compatible
          endpoint. AI runs on your own key, billed to your account{s?.mode === "user" ? "; a personal connection is required" : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.isPending || providers.isPending ? (
          <LoadingRows rows={2} />
        ) : status.isError ? (
          <ErrorState error={status.error} onRetry={() => status.refetch()} />
        ) : providers.isError ? (
          <ErrorState error={providers.error} onRetry={() => providers.refetch()} />
        ) : (
          <>
            <div className="text-sm">
              {s?.active ? (
                <span>
                  Using <span className="font-medium">{s.active.providerName}</span> · {s.active.model}
                  {s.active.free ? " · free" : ""}
                  {s.active.source === "server" ? " (shared server key)" : ""}
                </span>
              ) : (
                <Badge variant="outline">No AI connected: AI features are off</Badge>
              )}
            </div>
            {s && s.connections.length > 0 ? (
              <ul className="divide-y">
                {s.connections.map((c) => (
                  <ConnectionRow key={c.provider} connection={c} isOnly={s.connections.length === 1} />
                ))}
              </ul>
            ) : null}
            <ConnectProviderForm providers={providers.data} />
            <p className="text-xs text-muted-foreground">
              Keys are checked with the provider, stored encrypted and never shown again (only the last four characters). Set a
              spend limit with your provider too. Free models cost nothing in your AI budget; models without a known price are
              counted at Claude Opus rates so the budget still protects you.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ConsentsCard() {
  const queryClient = useQueryClient();
  const consents = useQuery({ queryKey: [...qk.settings, "consents"], queryFn: () => unwrap(api.GET("/api/v1/users/me/consents")) });
  const update = useMutation({
    mutationFn: ({ category, granted }: { category: ConsentCategory; granted: boolean }) =>
      unwrap(api.PUT("/api/v1/users/me/consents/{category}", { params: { path: { category } }, body: { granted } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.settings });
      void queryClient.invalidateQueries({ queryKey: qk.ai });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy and consent</CardTitle>
        <CardDescription>Every change is recorded in your audit log.</CardDescription>
      </CardHeader>
      <CardContent>
        {consents.isPending ? (
          <LoadingRows />
        ) : consents.isError ? (
          <ErrorState error={consents.error} onRetry={() => consents.refetch()} />
        ) : (
          <ul className="divide-y">
            {consents.data.map((c) => {
              const info = CONSENT_INFO[c.category];
              return (
                <li key={c.category} className="flex items-center gap-3 py-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium">{info.title}</p>
                    <p className="text-xs text-muted-foreground">{info.description}</p>
                  </div>
                  {info.available ? (
                    <Switch
                      checked={c.status === "granted"}
                      aria-label={info.title}
                      onCheckedChange={(granted) => update.mutate({ category: c.category, granted })}
                    />
                  ) : (
                    <Badge variant="outline">Not yet available</Badge>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function SessionsCard() {
  const queryClient = useQueryClient();
  const sessions = useQuery({ queryKey: [...qk.settings, "sessions"], queryFn: () => unwrap(api.GET("/api/v1/auth/sessions")) });
  const revoke = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/auth/sessions/{session_id}", { params: { path: { session_id: id } } })),
    onSuccess: () => {
      toast.success("Signed out of that device");
      void queryClient.invalidateQueries({ queryKey: qk.settings });
    },
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Signed-in devices</CardTitle>
        <CardDescription>Sign out anywhere you don&apos;t recognise.</CardDescription>
      </CardHeader>
      <CardContent>
        {sessions.isPending ? (
          <LoadingRows />
        ) : sessions.isError ? (
          <ErrorState error={sessions.error} />
        ) : (
          <ul className="divide-y text-sm">
            {sessions.data.map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate">{s.userAgent ?? "Unknown device"}</p>
                  <p className="text-xs text-muted-foreground">
                    Last active {new Date(s.lastSeenAt).toLocaleString()} · expires {new Date(s.expiresAt).toLocaleDateString()}
                  </p>
                </div>
                {s.current ? (
                  <Badge>This device</Badge>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => revoke.mutate(s.id)}>
                    Sign out
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function UsageCard() {
  const usage = useQuery({ queryKey: [...qk.ai, "usage"], queryFn: () => unwrap(api.GET("/api/v1/ai/usage")) });
  if (!usage.data) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>AI usage ({usage.data.month})</CardTitle>
        <CardDescription>
          ${usage.data.monthToDateUsd.toFixed(4)} of ${usage.data.monthlyBudgetUsd.toFixed(2)} budget. Costs are estimated from published token prices.
        </CardDescription>
      </CardHeader>
      {usage.data.byRoute.length ? (
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="py-1 font-normal">Route</th><th className="font-normal">Requests</th><th className="font-normal">Tokens in / out</th><th className="text-right font-normal">Cost</th></tr>
            </thead>
            <tbody className="tabular">
              {usage.data.byRoute.map((r) => (
                <tr key={r.route} className="border-t">
                  <td className="py-1.5">{r.route}</td>
                  <td>{r.requests}</td>
                  <td>{r.inputTokens.toLocaleString()} / {r.outputTokens.toLocaleString()}</td>
                  <td className="text-right">${r.costUsd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      ) : null}
    </Card>
  );
}

export default function SettingsPage() {
  const me = useMe();

  if (me.isPending) return <LoadingRows rows={6} />;
  if (me.isError) return <ErrorState error={me.error} onRetry={() => me.refetch()} />;
  return (
    <>
      <PageHeader title="Settings" description={me.data.user.email} />
      <div className="grid gap-4">
        <ProfileCard me={me.data} />
        <PreferencesCard me={me.data} />
        <AiProviderCard />
        <ConsentsCard />
        <UsageCard />
        <SessionsCard />
      </div>
    </>
  );
}
