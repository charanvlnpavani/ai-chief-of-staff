"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Briefcase,
  Library,
  CheckSquare,
  Eye,
  EyeOff,
  HeartPulse,
  LayoutDashboard,
  LayoutGrid,
  type LucideIcon,
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
import { useState } from "react";
import { useTheme } from "next-themes";

import { usePrivacy } from "@/components/privacy";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
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

type NavItem = {
  label: string;
  /** Short label for the mobile bar and the "More" sheet. */
  short?: string;
  icon: LucideIcon;
} & ({ href: string; release?: never } | { href?: never; release: string });

// Pages grouped by what they are about. Items with a `release` are on the roadmap:
// shown in their group so the plan is visible, but not clickable yet.
const SECTIONS: { title?: string; items: NavItem[] }[] = [
  {
    items: [
      { href: "/today", label: "Today", icon: LayoutDashboard },
      { href: "/chief", label: "Chief of Staff", short: "Chief", icon: Sparkles },
    ],
  },
  {
    title: "Plan",
    items: [
      { href: "/tasks", label: "Tasks", icon: CheckSquare },
      { href: "/habits", label: "Habits", icon: Repeat },
      { href: "/goals", label: "Goals", icon: Target },
      { href: "/roadmaps", label: "Roadmaps", icon: Route },
    ],
  },
  {
    title: "Knowledge",
    items: [{ href: "/library", label: "Library", icon: Library }],
  },
  {
    title: "Career & growth",
    items: [
      { href: "/work", label: "Work & learning", short: "Work", icon: BookOpen },
      { label: "Career", icon: Briefcase, release: "R3" },
      { label: "Growth", icon: Sprout, release: "R3" },
    ],
  },
  {
    title: "Wellbeing",
    items: [
      { label: "Health", icon: HeartPulse, release: "R2" },
      { label: "Finance", icon: Wallet, release: "R2" },
    ],
  },
  {
    title: "Connect",
    items: [
      { label: "Social", icon: Megaphone, release: "R6" },
      { label: "News", icon: Newspaper, release: "R6" },
    ],
  },
];

// The mobile bar keeps only the daily pages; everything else lives under "More".
const MOBILE_PRIMARY = ["/today", "/chief", "/tasks", "/habits"];
const MOBILE_PRIMARY_ITEMS = MOBILE_PRIMARY.map(
  (href) => SECTIONS.flatMap((s) => s.items).find((i) => i.href === href)!,
);

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

function SidebarItem({ item, pathname }: { item: NavItem; pathname: string }) {
  const { label, icon: Icon } = item;
  if (!item.href) {
    return (
      <span
        aria-disabled="true"
        title={`Coming in ${item.release}`}
        className="flex cursor-default items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground/60"
      >
        <Icon className="size-4" aria-hidden />
        {label}
        <span className="ml-auto rounded-full bg-muted px-1.5 py-px text-[10px] font-medium text-muted-foreground">
          {item.release}
        </span>
      </span>
    );
  }
  const active = isActive(pathname, item.href);
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
        active && "bg-sidebar-accent font-medium text-sidebar-foreground",
      )}
    >
      <Icon className="size-4" aria-hidden />
      {label}
    </Link>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  const [open, setOpen] = useState(false);
  const moreActive = !MOBILE_PRIMARY.some((href) => isActive(pathname, href));
  const tab = (active: boolean) =>
    cn(
      "relative flex min-h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium text-muted-foreground transition-colors",
      active && "text-primary",
    );

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {MOBILE_PRIMARY_ITEMS.map(({ href, label, short, icon: Icon }) => {
        const active = isActive(pathname, href!);
        return (
          <Link key={href} href={href!} aria-current={active ? "page" : undefined} className={tab(active)}>
            {active && <span className="absolute inset-x-5 top-0 h-0.5 rounded-full bg-primary" />}
            <Icon className="size-5" aria-hidden />
            {short ?? label}
          </Link>
        );
      })}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <button type="button" className={tab(moreActive)}>
            {moreActive && <span className="absolute inset-x-5 top-0 h-0.5 rounded-full bg-primary" />}
            <LayoutGrid className="size-5" aria-hidden />
            More
          </button>
        </SheetTrigger>
        <SheetContent side="bottom" className="max-h-[85vh] gap-0 overflow-y-auto rounded-t-2xl pb-[calc(env(safe-area-inset-bottom)+1rem)]">
          <SheetHeader className="pb-2">
            <SheetTitle>All sections</SheetTitle>
          </SheetHeader>
          <div className="flex flex-col gap-5 px-4">
            {SECTIONS.filter((s) => s.items.some((i) => !MOBILE_PRIMARY.includes(i.href ?? ""))).map(
              (section, i) => (
                <div key={section.title ?? i}>
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                    {section.title ?? "Daily"}
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {section.items
                      .filter((item) => !MOBILE_PRIMARY.includes(item.href ?? ""))
                      .map((item) => {
                        const { label, short, icon: Icon } = item;
                        const inner = (
                          <>
                            <Icon className="size-5" aria-hidden />
                            <span className="truncate">{short ?? label}</span>
                          </>
                        );
                        const base =
                          "relative flex flex-col items-center justify-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-medium";
                        if (!item.href) {
                          return (
                            <span
                              key={label}
                              aria-disabled="true"
                              className={cn(base, "border-dashed text-muted-foreground/60")}
                            >
                              {inner}
                              <span className="absolute right-1.5 top-1.5 rounded-full bg-muted px-1 text-[9px] text-muted-foreground">
                                {item.release}
                              </span>
                            </span>
                          );
                        }
                        const active = isActive(pathname, item.href);
                        return (
                          <Link
                            key={label}
                            href={item.href}
                            onClick={() => setOpen(false)}
                            aria-current={active ? "page" : undefined}
                            className={cn(
                              base,
                              "bg-card transition-colors hover:bg-accent",
                              active && "border-primary/50 bg-primary/10 text-primary",
                            )}
                          >
                            {inner}
                          </Link>
                        );
                      })}
                  </div>
                </div>
              ),
            )}
            <Link
              href="/settings"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-xl border bg-card px-3 py-2.5 text-sm hover:bg-accent"
            >
              <Settings className="size-4" aria-hidden /> Settings
            </Link>
          </div>
        </SheetContent>
      </Sheet>
    </nav>
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
        <nav aria-label="Main" className="-mx-1 flex flex-1 flex-col gap-5 overflow-y-auto px-1">
          {SECTIONS.map((section, i) => (
            <div key={section.title ?? i} className="flex flex-col gap-0.5">
              {section.title && (
                <p className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">
                  {section.title}
                </p>
              )}
              {section.items.map((item) => (
                <SidebarItem key={item.label} item={item} pathname={pathname} />
              ))}
            </div>
          ))}
        </nav>
        <div className="mt-4 border-t pt-3">
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

        <MobileNav pathname={pathname} />
      </div>
    </div>
  );
}
