"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Briefcase,
  CheckSquare,
  Eye,
  EyeOff,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Megaphone,
  Monitor,
  Moon,
  Newspaper,
  Repeat,
  Route,
  Settings,
  Sparkles,
  Sprout,
  Sun,
  Target,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import { usePrivacy } from "@/components/privacy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/today", label: "Today", icon: LayoutDashboard },
  { href: "/chief", label: "Chief of Staff", icon: Sparkles },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/habits", label: "Habits", icon: Repeat },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/roadmaps", label: "Roadmaps", icon: Route },
  { href: "/work", label: "Work & learning", icon: BookOpen },
] as const;

// Managers on the roadmap. Shown so the plan is visible, but not clickable yet.
const UPCOMING = [
  { label: "Finance", icon: Wallet, release: "R2" },
  { label: "Health", icon: HeartPulse, release: "R2" },
  { label: "Career", icon: Briefcase, release: "R3" },
  { label: "Growth", icon: Sprout, release: "R3" },
  { label: "Social", icon: Megaphone, release: "R6" },
  { label: "News", icon: Newspaper, release: "R6" },
] as const;

function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function UserMenu({ name, email }: { name: string; email: string }) {
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();

  async function signOut() {
    await api.POST("/api/v1/auth/logout");
    queryClient.clear();
    // A full reload (not client navigation) guarantees no personal data stays in memory.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2" aria-label="Account menu">
          <span className="grid size-7 place-content-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {name.slice(0, 1).toUpperCase()}
          </span>
          <span className="hidden max-w-32 truncate sm:inline">{name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="truncate font-medium">{name}</div>
          <div className="truncate text-xs text-muted-foreground">{email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Sun className="size-4" aria-hidden /> Light
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon className="size-4" aria-hidden /> Dark
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor className="size-4" aria-hidden /> System
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings className="size-4" aria-hidden /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={signOut}>
          <LogOut className="size-4" aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({
  user,
  children,
}: {
  /** Undefined while the session is still loading; the page itself renders regardless. */
  user?: { displayName: string; email: string };
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { hidden, toggle } = usePrivacy();

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>

      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-sidebar px-3 py-4 md:flex">
        <Link href="/today" className="mb-6 flex items-center gap-2 px-2 font-semibold">
          <span className="grid size-7 place-content-center rounded-lg bg-primary text-primary-foreground">
            <span className="size-2.5 rounded-full border-2 border-current" />
          </span>
          Personal OS
        </Link>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
                isActive(pathname, href) && "bg-sidebar-accent font-medium text-sidebar-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </Link>
          ))}
        </nav>
        <p className="mt-6 px-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Coming soon
        </p>
        <ul className="mt-1 flex flex-col gap-0.5" aria-label="Managers on the roadmap">
          {UPCOMING.map(({ label, icon: Icon, release }) => (
            <li
              key={label}
              className="flex items-center gap-2.5 px-2 py-1.5 text-sm text-muted-foreground/70"
            >
              <Icon className="size-4" aria-hidden />
              {label}
              <Badge variant="outline" className="ml-auto text-[10px]">
                {release}
              </Badge>
            </li>
          ))}
        </ul>
        <div className="mt-auto">
          <Link
            href="/settings"
            aria-current={isActive(pathname, "/settings") ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent",
              isActive(pathname, "/settings") && "bg-sidebar-accent font-medium",
            )}
          >
            <Settings className="size-4" aria-hidden /> Settings
          </Link>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur">
          <Link href="/today" className="font-semibold md:hidden">
            Personal OS
          </Link>
          <div className="ml-auto flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={toggle}
              aria-pressed={hidden}
              title="Privacy mode hides your numbers (useful when screen-sharing)"
            >
              {hidden ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
              <span className="hidden sm:inline">{hidden ? "Hidden" : "Privacy"}</span>
            </Button>
            {user ? (
              <UserMenu name={user.displayName} email={user.email} />
            ) : (
              <Skeleton className="h-8 w-24" aria-label="Loading account" />
            )}
          </div>
        </header>

        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 pb-24 pt-6 md:pb-10">
          {children}
        </main>

        <nav
          aria-label="Main"
          className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-7 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
        >
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={cn(
                "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground",
                isActive(pathname, href) && "text-primary",
              )}
            >
              <Icon className="size-5" aria-hidden />
              <span className="truncate">{label.split(" ")[0]}</span>
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}
