"use client";

import { AppShell } from "@/components/app-shell";
import { ErrorState } from "@/components/states";
import { useMe } from "@/lib/queries";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();

  if (me.isError) {
    // 401s redirect to /login inside unwrap(); anything else is shown here.
    return (
      <div className="mx-auto max-w-md p-6">
        <ErrorState error={me.error} onRetry={() => me.refetch()} />
      </div>
    );
  }
  // Always render the page, even while the session loads. Next.js validates each page's
  // prerendered state for instant navigation, and a layout that withholds `children` there
  // makes every page a "dropped segment". Pages show their own loading states, and their data
  // only comes from authenticated API calls (a 401 still redirects to /login).
  return <AppShell user={me.data?.user}>{children}</AppShell>;
}
