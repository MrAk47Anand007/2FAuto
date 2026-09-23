import { createFileRoute, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { LoadingState } from "@/components/common/states";
import { useAuth } from "@/features/auth/auth-context";

export const Route = createFileRoute("/app")({
  ssr: false,
  component: AppLayout,
});

function AppLayout() {
  const { status, isAdmin } = useAuth();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  useEffect(() => {
    if (status === "anonymous") void navigate({ to: "/login", replace: true });
  }, [status, navigate]);

  // Role-aware guard: ordinary users never land on an admin screen.
  useEffect(() => {
    if (status === "authenticated" && !isAdmin && pathname.startsWith("/app/admin")) {
      void navigate({ to: "/app/portals", replace: true });
    }
  }, [status, isAdmin, pathname, navigate]);

  if (status !== "authenticated") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <LoadingState rows={5} label="Restoring your session" />
      </div>
    );
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
