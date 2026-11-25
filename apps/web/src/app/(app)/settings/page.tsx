"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { usePrivacy } from "@/components/privacy";
import { ErrorState, LoadingRows, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage, unwrap, type Schemas } from "@/lib/api";
import { qk, useMe } from "@/lib/queries";

type Me = Schemas["MeOut"];
type ConsentCategory = Schemas["ConsentOut"]["category"];

const CONSENT_INFO: Record<ConsentCategory, { title: string; description: string; available: boolean }> = {
  ai_processing: {
    title: "Chief of Staff (AI)",
    description: "Lets Claude read your tasks, habits, learning and practice records when you ask it something.",
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
        <ConsentsCard />
        <UsageCard />
        <SessionsCard />
      </div>
    </>
  );
}
