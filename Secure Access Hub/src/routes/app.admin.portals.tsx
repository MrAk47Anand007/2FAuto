import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Search, UserPlus } from "lucide-react";
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
import { Field } from "@/components/common/field";
import { useStepUpAction } from "@/features/auth/step-up";
import * as api from "@/lib/api/endpoints";
import type { AdminPortal } from "@/lib/api/types";

export const Route = createFileRoute("/app/admin/portals")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Portals — 2FAuto admin" },
      {
        name: "description",
        content: "Create, edit, disable, and grant access to shared OTP portals.",
      },
      { property: "og:title", content: "Portals — 2FAuto admin" },
      { property: "og:description", content: "Manage shared OTP portals and who can use them." },
    ],
  }),
  component: AdminPortalsPage,
});

const createSchema = z.object({
  portal_name: z
    .string()
    .min(2, "At least 2 characters")
    .regex(/^[a-z0-9-]+$/, "Lowercase letters, numbers, and hyphens only"),
  display_name: z.string().min(1, "Enter a display name"),
  secret: z.string().min(1, "Enter a Base32 seed or otpauth:// URI"),
  period: z.coerce.number().int().min(10, "Minimum 10 seconds").max(120, "Maximum 120 seconds"),
});
type CreateValues = z.infer<typeof createSchema>;

const grantSchema = z.object({
  username: z.string().min(1, "Enter a username"),
  expires_in_days: z.coerce.number().int().min(0).max(3650),
});
type GrantValues = z.infer<typeof grantSchema>;

function AdminPortalsPage() {
  const queryClient = useQueryClient();
  const { perform, dialog } = useStepUpAction();
  const [term, setTerm] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [grantFor, setGrantFor] = useState<AdminPortal | null>(null);
  const [confirm, setConfirm] = useState<{
    title: string;
    description: string;
    label: string;
    run: () => Promise<unknown>;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const query = useQuery({ queryKey: ["admin", "portals"], queryFn: api.adminListPortals });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "portals"] });

  const portals = useMemo(() => {
    const all = query.data?.portals ?? [];
    const needle = term.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      (portal) =>
        portal.display_name.toLowerCase().includes(needle) || portal.portal_name.includes(needle),
    );
  }, [query.data, term]);

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { portal_name: "", display_name: "", secret: "", period: 30 },
  });

  const grantForm = useForm<GrantValues>({
    resolver: zodResolver(grantSchema),
    defaultValues: { username: "", expires_in_days: 30 },
  });

  const submitCreate = createForm.handleSubmit(async (values) => {
    const ok = await perform("Create portal", () => api.adminCreatePortal(values));
    // The seed never stays in memory, whether the call succeeded or not.
    createForm.setValue("secret", "");
    if (ok) {
      toast.success(`Portal "${values.display_name}" created.`);
      createForm.reset({ portal_name: "", display_name: "", secret: "", period: 30 });
      setCreateOpen(false);
      void refresh();
    }
  });

  const submitGrant = grantForm.handleSubmit(async (values) => {
    if (!grantFor) return;
    const ok = await perform("Grant access", () =>
      api.adminGrantPortal(grantFor.portal_name, values),
    );
    if (ok) {
      toast.success(`Access granted to ${values.username}.`);
      grantForm.reset({ username: "", expires_in_days: 30 });
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

  return (
    <>
      <PageHeader
        title="Portals"
        description="Shared logins protected by time-based codes. Seeds are write-only and never shown again."
        actions={
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="size-4" aria-hidden />
                New portal
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Create portal</DialogTitle>
                <DialogDescription>
                  The seed is stored encrypted and can never be displayed again after creation.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submitCreate} className="space-y-4" noValidate>
                <Field
                  label="Identifier"
                  error={createForm.formState.errors.portal_name?.message}
                  id="portal_name"
                >
                  <Input
                    id="portal_name"
                    placeholder="vendor-login"
                    {...createForm.register("portal_name")}
                  />
                </Field>
                <Field
                  label="Display name"
                  error={createForm.formState.errors.display_name?.message}
                  id="display_name"
                >
                  <Input
                    id="display_name"
                    placeholder="Vendor Login"
                    {...createForm.register("display_name")}
                  />
                </Field>
                <Field
                  label="Seed (Base32 or otpauth:// URI)"
                  error={createForm.formState.errors.secret?.message}
                  id="secret"
                >
                  <Input
                    id="secret"
                    type="password"
                    autoComplete="off"
                    {...createForm.register("secret")}
                  />
                </Field>
                <Field
                  label="Period (seconds)"
                  error={createForm.formState.errors.period?.message}
                  id="period"
                >
                  <Input
                    id="period"
                    type="number"
                    min={10}
                    max={120}
                    {...createForm.register("period")}
                  />
                </Field>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={createForm.formState.isSubmitting}>
                    Create portal
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Filter loaded portals"
          aria-label="Filter loaded portals"
          className="pl-9"
        />
      </div>

      <Panel>
        {query.isPending ? (
          <LoadingState label="Loading portals" />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : portals.length === 0 ? (
          <EmptyState
            title="No portals"
            description="Create a portal to start issuing shared codes."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Portal</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Direct grants</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portals.map((portal) => {
                  const active = portal.status !== "disabled";
                  return (
                    <TableRow key={portal.portal_name}>
                      <TableCell>
                        <p className="text-sm font-medium">{portal.display_name}</p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {portal.portal_name}
                        </p>
                      </TableCell>
                      <TableCell className="text-sm">{portal.period}s</TableCell>
                      <TableCell className="text-sm">
                        {portal.grants.length === 0 ? (
                          <span className="text-muted-foreground">None</span>
                        ) : (
                          <ul className="space-y-1">
                            {portal.grants.map((grant) => (
                              <li
                                key={`${grant.username}-${grant.source}`}
                                className="flex items-center gap-2"
                              >
                                <span className="font-mono text-xs">{grant.username}</span>
                                <span className="rounded border border-border px-1.5 text-[11px] text-muted-foreground">
                                  {grant.source === "team"
                                    ? `via ${grant.team_name ?? "team"}`
                                    : "direct"}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {grant.expires_at
                                    ? `until ${formatMoment(grant.expires_at)}`
                                    : "no expiry"}
                                </span>
                                {grant.source === "direct" ? (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-6 px-2 text-xs"
                                    onClick={() =>
                                      setConfirm({
                                        title: `Revoke ${grant.username}'s direct access?`,
                                        description:
                                          "If this person is also in a team with access to this portal, that team grant will keep their access active.",
                                        label: "Revoke grant",
                                        run: () =>
                                          api.adminRevokePortalGrant(
                                            portal.portal_name,
                                            grant.username,
                                          ),
                                      })
                                    }
                                  >
                                    Revoke
                                  </Button>
                                ) : null}
                              </li>
                            ))}
                          </ul>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge active={active} />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button variant="outline" size="sm" onClick={() => setGrantFor(portal)}>
                            <UserPlus className="size-4" aria-hidden />
                            Grant
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setConfirm({
                                title: active
                                  ? `Disable ${portal.display_name}?`
                                  : `Reactivate ${portal.display_name}?`,
                                description: active
                                  ? "Nobody will be able to reveal codes for this portal until it is reactivated."
                                  : "Everyone with an active grant will be able to reveal codes again.",
                                label: active ? "Disable portal" : "Reactivate portal",
                                run: () =>
                                  api.adminPortalAction(
                                    portal.portal_name,
                                    active ? "disable" : "reactivate",
                                  ),
                              })
                            }
                          >
                            {active ? "Disable" : "Reactivate"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive"
                            onClick={() =>
                              setConfirm({
                                title: `Delete ${portal.display_name}?`,
                                description:
                                  "The portal, its seed, and all of its grants are removed permanently. This cannot be undone.",
                                label: "Delete portal",
                                run: () => api.adminPortalAction(portal.portal_name, "delete"),
                              })
                            }
                          >
                            Delete
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>

      <Dialog open={grantFor !== null} onOpenChange={(open) => (open ? null : setGrantFor(null))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Grant access to {grantFor?.display_name}</DialogTitle>
            <DialogDescription>
              Use 0 days for access that never expires (maximum 3650).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitGrant} className="space-y-4" noValidate>
            <Field
              label="Username"
              error={grantForm.formState.errors.username?.message}
              id="grant-username"
            >
              <Input id="grant-username" {...grantForm.register("username")} />
            </Field>
            <Field
              label="Expires in (days)"
              error={grantForm.formState.errors.expires_in_days?.message}
              id="grant-days"
            >
              <Input
                id="grant-days"
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
