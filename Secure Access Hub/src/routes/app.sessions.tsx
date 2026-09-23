import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
  formatMoment,
} from "@/components/common/states";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { listSessions, revokeSession } from "@/lib/api/endpoints";
import { errorMessage } from "@/lib/api/client";
import { useAuth } from "@/features/auth/auth-context";

export const Route = createFileRoute("/app/sessions")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "My Sessions — 2FAuto" },
      {
        name: "description",
        content: "Review and revoke the browser sessions signed in to your 2FAuto account.",
      },
      { property: "og:title", content: "My Sessions — 2FAuto" },
      { property: "og:description", content: "Review and revoke your active 2FAuto sessions." },
    ],
  }),
  component: SessionsPage,
});

function SessionsPage() {
  const queryClient = useQueryClient();
  const { signOut } = useAuth();
  const [pending, setPending] = useState<{ id: string; current: boolean } | null>(null);

  const query = useQuery({ queryKey: ["me", "sessions"], queryFn: listSessions });

  const revoke = useMutation({
    mutationFn: (sessionId: string) => revokeSession(sessionId),
    onSuccess: async (_data, sessionId) => {
      const wasCurrent = pending?.current && pending.id === sessionId;
      setPending(null);
      if (wasCurrent) {
        toast.success("Session revoked. Signing you out.");
        await signOut();
        return;
      }
      toast.success("Session revoked.");
      await queryClient.invalidateQueries({ queryKey: ["me", "sessions"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  const sessions = query.data?.sessions ?? [];

  return (
    <>
      <PageHeader
        title="My Sessions"
        description="Every browser signed in with your account. Revoking a session ends it immediately."
      />

      <Panel>
        {query.isPending ? (
          <LoadingState label="Loading your sessions" />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : sessions.length === 0 ? (
          <EmptyState
            title="No sessions found"
            description="There are no recorded sessions for this account."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Last active</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((session) => {
                  const revoked = Boolean(session.revoked_at);
                  return (
                    <TableRow key={session.id}>
                      <TableCell className="font-mono text-xs">
                        {session.id.slice(0, 12)}…
                        {session.current ? (
                          <span className="ml-2 rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                            This device
                          </span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm">{formatMoment(session.created_at)}</TableCell>
                      <TableCell className="text-sm">
                        {formatMoment(session.last_active_at)}
                      </TableCell>
                      <TableCell className="text-sm">{formatMoment(session.expires_at)}</TableCell>
                      <TableCell>
                        <StatusBadge
                          active={!revoked}
                          activeLabel="Active"
                          inactiveLabel="Revoked"
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={revoked || revoke.isPending}
                          onClick={() => setPending({ id: session.id, current: session.current })}
                        >
                          Revoke
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => (open ? null : setPending(null))}
        title={pending?.current ? "Revoke this device's session?" : "Revoke this session?"}
        description={
          pending?.current
            ? "This is the session you are using. You will be signed out immediately."
            : "That browser will be signed out immediately and must sign in again."
        }
        confirmLabel="Revoke session"
        destructive
        busy={revoke.isPending}
        onConfirm={() => pending && revoke.mutate(pending.id)}
      />
    </>
  );
}
