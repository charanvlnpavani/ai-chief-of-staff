import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginCard } from "./login-card";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-muted/30 p-4">
      <Suspense fallback={null}>
        <LoginCard />
      </Suspense>
    </main>
  );
}
