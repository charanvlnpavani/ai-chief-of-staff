"use client";

import { AppShell } from "@/components/app-shell";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/queries";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();

  if (me.isPending) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 p-6" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    );
  }
  if (me.isError) {
    // 401s redirect to /login inside unwrap(); anything else is shown here.
    return (
      <div className="mx-auto max-w-md p-6">
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      </div>
    );
  }
  return <AppShell user={me.data.user}>{children}</AppShell>;
}
