import { useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Bot,
  KeyRound,
  LogOut,
  Menu,
  MonitorSmartphone,
  ScrollText,
  ShieldCheck,
  Users,
  UsersRound,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/features/auth/auth-context";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof KeyRound;
}

const USER_NAV: NavItem[] = [
  { to: "/app/portals", label: "My Portals", icon: KeyRound },
  { to: "/app/sessions", label: "My Sessions", icon: MonitorSmartphone },
];

const ADMIN_NAV: NavItem[] = [
  { to: "/app/admin/portals", label: "Portals", icon: ShieldCheck },
  { to: "/app/admin/people", label: "People", icon: Users },
  { to: "/app/admin/teams", label: "Teams & Access", icon: UsersRound },
  { to: "/app/admin/clients", label: "Automation Clients", icon: Bot },
  { to: "/app/admin/audit", label: "Audit Events", icon: ScrollText },
];

function NavLinks({
  items,
  onNavigate,
}: {
  items: NavItem[];
  onNavigate?: (() => void) | undefined;
}) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => (
        <li key={item.to}>
          <Link
            to={item.to}
            onClick={onNavigate}
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground data-[status=active]:bg-sidebar-accent data-[status=active]:font-medium data-[status=active]:text-sidebar-accent-foreground"
            activeProps={{ "aria-current": "page" }}
          >
            <item.icon className="size-4 shrink-0" aria-hidden />
            {item.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: (() => void) | undefined }) {
  const { user, isAdmin, signOut } = useAuth();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-5 py-5">
        <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-primary">
          <ShieldCheck className="size-4 text-sidebar-primary-foreground" aria-hidden />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold text-sidebar-accent-foreground">2FAuto</p>
          <p className="text-xs text-sidebar-foreground/70">Shared OTP access</p>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4" aria-label="Main">
        <div>
          <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wider text-sidebar-foreground/55">
            Workspace
          </p>
          <NavLinks items={USER_NAV} onNavigate={onNavigate} />
        </div>
        {isAdmin ? (
          <div>
            <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wider text-sidebar-foreground/55">
              Administration
            </p>
            <NavLinks items={ADMIN_NAV} onNavigate={onNavigate} />
          </div>
        ) : null}
      </nav>

      <Separator className="bg-sidebar-border" />
      <div className="space-y-3 p-4">
        <div className="text-sm">
          <p className="font-medium text-sidebar-accent-foreground">{user?.username}</p>
          <p className="text-xs capitalize text-sidebar-foreground/70">{user?.role} account</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start border-sidebar-border bg-transparent text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          onClick={() => void signOut()}
        >
          <LogOut className="size-4" aria-hidden />
          Sign out
        </Button>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-sidebar-border bg-sidebar lg:block">
        <SidebarContent />
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-foreground/40"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 bg-sidebar shadow-xl">
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-3 text-sidebar-foreground hover:bg-sidebar-accent"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
            >
              <X className="size-4" aria-hidden />
            </Button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="lg:pl-64">
        <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-3 lg:hidden">
          <Button
            variant="outline"
            size="icon"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-4" aria-hidden />
          </Button>
          <span className="text-sm font-semibold">2FAuto</span>
        </div>
        <main
          key={pathname}
          className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-8"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
