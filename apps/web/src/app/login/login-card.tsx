"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { LogIn } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, errorMessage, unwrap } from "@/lib/api";

const ERRORS: Record<string, string> = {
  not_allowed: "This Google account is not on the sign-in allowlist (ALLOWED_LOGIN_EMAILS).",
  state_expired: "The sign-in took too long. Please try again.",
  state_mismatch: "The sign-in could not be verified. Please try again.",
  google_cancelled: "Google sign-in was cancelled.",
  email_not_verified: "Your Google email address is not verified.",
  google_unreachable: "Could not reach Google. Check your connection and try again.",
};

function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/today";
}

export function LoginCard() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const errorCode = params.get("error");

  const config = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => unwrap(api.GET("/api/v1/auth/config")),
  });
  const devLogin = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/dev/login", { body: {} })),
    onSuccess: () => window.location.assign(next),
  });

  const neither = config.data && !config.data.googleEnabled && !config.data.devLoginEnabled;

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="text-center">
        <div className="mx-auto mb-2 grid size-10 place-content-center rounded-xl bg-primary text-primary-foreground">
          <span className="size-3.5 rounded-full border-2 border-current" />
        </div>
        <CardTitle className="text-xl">Personal OS</CardTitle>
        <CardDescription>One platform. Eight managers. One Chief of Staff.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {errorCode ? (
          <Alert variant="destructive">
            <AlertDescription>{ERRORS[errorCode] ?? "Sign-in failed. Please try again."}</AlertDescription>
          </Alert>
        ) : null}
        {config.data?.googleEnabled ? (
          <Button asChild className="w-full">
            <a href={`/api/v1/auth/google/start?next=${encodeURIComponent(next)}`}>
              Continue with Google
            </a>
          </Button>
        ) : null}
        {config.data?.devLoginEnabled ? (
          <Button
            variant="outline"
            className="w-full"
            disabled={devLogin.isPending}
            onClick={() => devLogin.mutate()}
          >
            <LogIn className="size-4" aria-hidden />
            {devLogin.isPending ? "Signing in…" : "Continue (local development)"}
          </Button>
        ) : null}
        {devLogin.isError ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(devLogin.error)}
          </p>
        ) : null}
        {config.isError ? (
          <p role="alert" className="text-sm text-destructive">
            The API is not reachable. Start it with <code>pnpm dev</code>.
          </p>
        ) : null}
        {neither ? (
          <p className="text-sm text-muted-foreground">
            No sign-in method is configured. Set GOOGLE_CLIENT_ID/SECRET or DEV_LOGIN_ENABLED in
            backend/.env.
          </p>
        ) : null}
        <p className="pt-2 text-center text-xs text-muted-foreground">
          Private by design: your data stays in your own database.
        </p>
      </CardContent>
    </Card>
  );
}
