import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  formatMoment,
} from "@/components/common/states";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Field } from "@/components/common/field";
import { useStepUpAction } from "@/features/auth/step-up";
import * as api from "@/lib/api/endpoints";

export const Route = createFileRoute("/app/admin/teams")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Teams & Access — 2FAuto admin" },
      {
        name: "description",
        content: "Group people into teams and grant portal access to whole teams at once.",
      },
      { property: "og:title", content: "Teams & Access — 2FAuto admin" },
      {
        property: "og:description",
        content: "Manage team membership and inherited portal access.",
      },
    ],
  }),
  component: TeamsPage,
});

const teamSchema = z.object({ name: z.string().min(2, "At least 2 characters") });
const memberSchema = z.object({ username: z.string().min(1, "Enter a username") });
const grantSchema = z.object({
  portal_name: z.string().min(1, "Choose a portal"),
  expires_in_days: z.coerce.number().int().min(0).max(3650),
});

function TeamsPage() {
  const queryClient = useQueryClient();
  const { perform, dialog } = useStepUpAction();
  const [createOpen, setCreateOpen] = useState(false);
  const [memberFor, setMemberFor] = useState<string | null>(null);
  const [grantFor, setGrantFor] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{
    title: string;
    description: string;
    label: string;
    run: () => Promise<unknown>;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const teamsQuery = useQuery({ queryKey: ["admin", "teams"], queryFn: api.adminListTeams });
  const portalsQuery = useQuery({ queryKey: ["admin", "portals"], queryFn: api.adminListPortals });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "teams"] });

  const teamForm = useForm<z.infer<typeof teamSchema>>({
    resolver: zodResolver(teamSchema),
    defaultValues: { name: "" },
  });
  const memberForm = useForm<z.infer<typeof memberSchema>>({
    resolver: zodResolver(memberSchema),
    defaultValues: { username: "" },
  });
  const grantForm = useForm<z.infer<typeof grantSchema>>({
    resolver: zodResolver(grantSchema),
    defaultValues: { portal_name: "", expires_in_days: 30 },
  });

  const submitTeam = teamForm.handleSubmit(async (values) => {
    const ok = await perform("Create team", () => api.adminCreateTeam(values.name));
    if (ok) {
      toast.success(`Team "${values.name}" created.`);
      teamForm.reset({ name: "" });
      setCreateOpen(false);
      void refresh();
    }
  });

  const submitMember = memberForm.handleSubmit(async (values) => {
    if (!memberFor) return;
    const ok = await perform("Add member", () =>
      api.adminAddTeamMember(memberFor, values.username),
    );
    if (ok) {
      toast.success(`${values.username} added to ${memberFor}.`);
      memberForm.reset({ username: "" });
      setMemberFor(null);
      void refresh();
    }
  });

  const submitGrant = grantForm.handleSubmit(async (values) => {
    if (!grantFor) return;
    const ok = await perform("Grant team access", () =>
      api.adminGrantTeamPortal(grantFor, values.portal_name, values.expires_in_days),
    );
    if (ok) {
      toast.success("Team access granted.");
      grantForm.reset({ portal_name: "", expires_in_days: 30 });
      setGrantFor(null);
      void refresh();
    }
  });

  const runConfirmed = async () => {
    if (!confirm) return;
    setBusy(true);
    const ok = await perform(confirm.label, confirm.run);
    setBusy(false);
    setConfirm(null);
    if (ok) {
      toast.success("Done.");
      void refresh();
    }
  };

  const teams = teamsQuery.data?.teams ?? [];

  return (
    <>
      <PageHeader
        title="Teams & Access"
        description="Team grants are inherited by every member. A person may also hold a direct grant to the same portal."
        actions={
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="size-4" aria-hidden />
                New team
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Create team</DialogTitle>
                <DialogDescription>
                  Teams group people so access can be granted once.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submitTeam} className="space-y-4" noValidate>
                <Field
                  label="Team name"
                  id="team-name"
                  error={teamForm.formState.errors.name?.message}
                >
                  <Input id="team-name" {...teamForm.register("name")} />
                </Field>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit">Create team</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      {teamsQuery.isPending ? (
        <Panel>
          <LoadingState label="Loading teams" />
        </Panel>
      ) : teamsQuery.isError ? (
        <Panel>
          <ErrorState error={teamsQuery.error} onRetry={() => void teamsQuery.refetch()} />
        </Panel>
      ) : teams.length === 0 ? (
        <Panel>
          <EmptyState
            title="No teams yet"
            description="Create a team to grant portal access to several people at once."
          />
        </Panel>
      ) : (
        <div className="space-y-4">
          {teams.map((team) => (
            <Panel key={team.name} className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-semibold">{team.name}</h2>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setMemberFor(team.name)}>
                    Add member
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setGrantFor(team.name)}>
                    Grant portal
                  </Button>
                </div>
              </div>

              <div className="mt-5 grid gap-6 md:grid-cols-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Members
                  </p>
                  {team.members.length === 0 ? (
                    <p className="mt-2 text-sm text-muted-foreground">No members yet.</p>
                  ) : (
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {team.members.map((member) => (
                        <li
                          key={member}
                          className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 py-1 pl-3 pr-1 text-sm"
                        >
                          {member}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-6"
                            aria-label={`Remove ${member} from ${team.name}`}
                            onClick={() =>
                              setConfirm({
                                title: `Remove ${member} from ${team.name}?`,
                                description:
                                  "They lose every portal this team grants. Any direct grant they hold stays active.",
                                label: "Remove member",
                                run: () => api.adminRemoveTeamMember(team.name, member),
                              })
                            }
                          >
                            <X className="size-3.5" aria-hidden />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Portal access
                  </p>
                  {team.grants.length === 0 ? (
                    <p className="mt-2 text-sm text-muted-foreground">
                      No portals granted to this team.
                    </p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {team.grants.map((grant) => (
                        <li
                          key={grant.portal_name}
                          className="flex items-center justify-between gap-3 text-sm"
                        >
                          <span className="font-mono text-xs">{grant.portal_name}</span>
                          <span className="text-xs text-muted-foreground">
                            {grant.expires_at
                              ? `until ${formatMoment(grant.expires_at)}`
                              : "no expiry"}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() =>
                              setConfirm({
                                title: `Revoke ${grant.portal_name} from ${team.name}?`,
                                description:
                                  "Members lose this inherited access. Anyone holding a direct grant to the same portal keeps it.",
                                label: "Revoke team grant",
                                run: () => api.adminRevokeTeamGrant(team.name, grant.portal_name),
                              })
                            }
                          >
                            Revoke
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </Panel>
          ))}
        </div>
      )}

      <Dialog open={memberFor !== null} onOpenChange={(open) => (open ? null : setMemberFor(null))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add member to {memberFor}</DialogTitle>
            <DialogDescription>
              The person inherits every portal granted to this team.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitMember} className="space-y-4" noValidate>
            <Field
              label="Username"
              id="member-username"
              error={memberForm.formState.errors.username?.message}
            >
              <Input id="member-username" {...memberForm.register("username")} />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setMemberFor(null)}>
                Cancel
              </Button>
              <Button type="submit">Add member</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={grantFor !== null} onOpenChange={(open) => (open ? null : setGrantFor(null))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Grant portal access to {grantFor}</DialogTitle>
            <DialogDescription>
              Use 0 days for access that never expires (maximum 3650).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitGrant} className="space-y-4" noValidate>
            <Field
              label="Portal"
              id="team-grant-portal"
              error={grantForm.formState.errors.portal_name?.message}
            >
              <Select
                value={grantForm.watch("portal_name")}
                onValueChange={(value) => grantForm.setValue("portal_name", value)}
              >
                <SelectTrigger id="team-grant-portal">
                  <SelectValue placeholder="Choose a portal" />
                </SelectTrigger>
                <SelectContent>
                  {(portalsQuery.data?.portals ?? []).map((portal) => (
                    <SelectItem key={portal.portal_name} value={portal.portal_name}>
                      {portal.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field
              label="Expires in (days)"
              id="team-grant-days"
              error={grantForm.formState.errors.expires_in_days?.message}
            >
              <Input
                id="team-grant-days"
                type="number"
                min={0}
                max={3650}
                {...grantForm.register("expires_in_days")}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setGrantFor(null)}>
                Cancel
              </Button>
              <Button type="submit">Grant access</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => (open ? null : setConfirm(null))}
        title={confirm?.title ?? ""}
        description={confirm?.description ?? ""}
        confirmLabel={confirm?.label}
        destructive
        busy={busy}
        onConfirm={() => void runConfirmed()}
      />

      {dialog}
    </>
  );
}
