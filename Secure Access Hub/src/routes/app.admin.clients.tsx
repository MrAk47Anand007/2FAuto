import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Check, Copy, Plus } from "lucide-react";
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
import type { AutomationClient } from "@/lib/api/types";

export const Route = createFileRoute("/app/admin/clients")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Automation Clients — 2FAuto admin" },
      {
        name: "description",
        content: "Issue and revoke machine credentials that retrieve codes without a browser.",
      },
      { property: "og:title", content: "Automation Clients — 2FAuto admin" },
      {
        property: "og:description",
        content: "Manage machine credentials for automated code retrieval.",
      },
    ],
  }),
  component: ClientsPage,
});

const clientSchema = z.object({
  name: z.string().min(2, "At least 2 characters"),
  environment: z.string().min(1, "Enter an environment"),
  expires_in_days: z.coerce.number().int().min(0).max(3650),
});

const credentialSchema = z.object({
  expires_in_days: z.coerce.number().int().min(1, "At least 1 day").max(3650),
});

const grantSchema = z.object({
  portal_name: z.string().min(1, "Choose a portal"),
  expires_in_days: z.coerce.number().int().min(0).max(3650),
});

function ClientsPage() {
  const queryClient = useQueryClient();
  const { perform, dialog } = useStepUpAction();
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<AutomationClient | null>(null);
  const [issueFor, setIssueFor] = useState<AutomationClient | null>(null);
  const [grantFor, setGrantFor] = useState<AutomationClient | null>(null);
  /** One-time visible credential. Component memory only, never cached. */
  const [issued, setIssued] = useState<{ client: string; value: string; warning?: string } | null>(
    null,
  );
  const [copied, setCopied] = useState(false);
  const [confirm, setConfirm] = useState<{
    title: string;
    description: string;
    label: string;
    run: () => Promise<unknown>;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const clientsQuery = useQuery({ queryKey: ["clients"], queryFn: api.listClients });
  const portalsQuery = useQuery({ queryKey: ["admin", "portals"], queryFn: api.adminListPortals });
  const credentialsQuery = useQuery({
    queryKey: ["clients", selected?.id, "credentials"],
    queryFn: () => api.listClientCredentials(selected!.id),
    enabled: selected !== null,
  });

  const refreshClients = () => queryClient.invalidateQueries({ queryKey: ["clients"] });

  const clientForm = useForm<z.infer<typeof clientSchema>>({
    resolver: zodResolver(clientSchema),
    defaultValues: { name: "", environment: "production", expires_in_days: 90 },
  });
  const credentialForm = useForm<z.infer<typeof credentialSchema>>({
    resolver: zodResolver(credentialSchema),
    defaultValues: { expires_in_days: 90 },
  });
  const grantForm = useForm<z.infer<typeof grantSchema>>({
    resolver: zodResolver(grantSchema),
    defaultValues: { portal_name: "", expires_in_days: 30 },
  });

  const submitClient = clientForm.handleSubmit(async (values) => {
    const ok = await perform("Create client", () => api.createClient(values));
    if (ok) {
      toast.success(`Client "${values.name}" created.`);
      clientForm.reset({ name: "", environment: "production", expires_in_days: 90 });
      setCreateOpen(false);
      void refreshClients();
    }
  });

  const submitCredential = credentialForm.handleSubmit(async (values) => {
    if (!issueFor) return;
    const client = issueFor;
    // Credential issuance is never retried automatically.
    const ok = await perform("Issue credential", async () => {
      const result = await api.issueClientCredential(client.id, values.expires_in_days);
      setIssued({
        client: client.name,
        value: result.credential,
        ...(result.warning ? { warning: result.warning } : {}),
      });
      return result;
    });
    if (ok) {
      setIssueFor(null);
      void queryClient.invalidateQueries({ queryKey: ["clients", client.id, "credentials"] });
    }
  });

  const submitGrant = grantForm.handleSubmit(async (values) => {
    if (!grantFor) return;
    const ok = await perform("Grant portal access", () =>
      api.grantClientPortal(grantFor.id, values.portal_name, values.expires_in_days),
    );
    if (ok) {
      toast.success("Portal access granted to the client.");
      grantForm.reset({ portal_name: "", expires_in_days: 30 });
      setGrantFor(null);
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
      void refreshClients();
      if (selected)
        void queryClient.invalidateQueries({ queryKey: ["clients", selected.id, "credentials"] });
    }
  };

  const clients = clientsQuery.data?.clients ?? [];

  return (
    <>
      <PageHeader
        title="Automation Clients"
        description="Machine identities that fetch codes over the API. Credentials are shown once, at issue time only."
        actions={
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="size-4" aria-hidden />
                New client
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Create automation client</DialogTitle>
                <DialogDescription>
                  Use 0 days for a client that never expires (maximum 3650).
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submitClient} className="space-y-4" noValidate>
                <Field
                  label="Name"
                  id="client-name"
                  error={clientForm.formState.errors.name?.message}
                >
                  <Input
                    id="client-name"
                    placeholder="a360-client"
                    {...clientForm.register("name")}
                  />
                </Field>
                <Field
                  label="Environment"
                  id="client-env"
                  error={clientForm.formState.errors.environment?.message}
                >
                  <Input
                    id="client-env"
                    placeholder="production"
                    {...clientForm.register("environment")}
                  />
                </Field>
                <Field
                  label="Expires in (days)"
                  id="client-days"
                  error={clientForm.formState.errors.expires_in_days?.message}
                >
                  <Input
                    id="client-days"
                    type="number"
                    min={0}
                    max={3650}
                    {...clientForm.register("expires_in_days")}
                  />
                </Field>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit">Create client</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        }
      />

      <Panel>
        {clientsQuery.isPending ? (
          <LoadingState label="Loading clients" />
        ) : clientsQuery.isError ? (
          <ErrorState error={clientsQuery.error} onRetry={() => void clientsQuery.refetch()} />
        ) : clients.length === 0 ? (
          <EmptyState
            title="No automation clients"
            description="Create a client to let a bot retrieve codes."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Client</TableHead>
                  <TableHead>Environment</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clients.map((client) => {
                  const active = !client.revoked_at && client.status !== "revoked";
                  return (
                    <TableRow key={client.id}>
                      <TableCell className="text-sm font-medium">{client.name}</TableCell>
                      <TableCell className="text-sm">{client.environment}</TableCell>
                      <TableCell className="text-sm">{formatMoment(client.created_at)}</TableCell>
                      <TableCell className="text-sm">
                        {client.expires_at ? formatMoment(client.expires_at) : "No expiry"}
                      </TableCell>
                      <TableCell>
                        <StatusBadge active={active} activeLabel="Active" inactiveLabel="Revoked" />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setSelected(selected?.id === client.id ? null : client)}
                          >
                            {selected?.id === client.id ? "Hide credentials" : "Credentials"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={!active}
                            onClick={() => setGrantFor(client)}
                          >
                            Grant portal
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-destructive"
                            disabled={!active}
                            onClick={() =>
                              setConfirm({
                                title: `Revoke ${client.name}?`,
                                description:
                                  "The client and all of its credentials stop working immediately. Automations using it will fail.",
                                label: "Revoke client",
                                run: () => api.revokeClient(client.id),
                              })
                            }
                          >
                            Revoke
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

      {selected ? (
        <Panel className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Credentials — {selected.name}</h2>
              <p className="text-xs text-muted-foreground">
                Existing secrets are never retrievable. Issue a new credential and rotate the old
                one out.
              </p>
            </div>
            <Button size="sm" onClick={() => setIssueFor(selected)}>
              Issue credential
            </Button>
          </div>

          <div className="mt-4">
            {credentialsQuery.isPending ? (
              <LoadingState rows={2} label="Loading credentials" />
            ) : credentialsQuery.isError ? (
              <ErrorState
                error={credentialsQuery.error}
                onRetry={() => void credentialsQuery.refetch()}
              />
            ) : (credentialsQuery.data?.credentials ?? []).length === 0 ? (
              <EmptyState
                title="No credentials issued"
                description="Issue one to let this client authenticate."
              />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Issued</TableHead>
                      <TableHead>Expires</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(credentialsQuery.data?.credentials ?? []).map((credential) => {
                      const active = !credential.revoked_at;
                      return (
                        <TableRow key={credential.id}>
                          <TableCell className="font-mono text-xs">{credential.id}</TableCell>
                          <TableCell className="text-sm">
                            {formatMoment(credential.created_at)}
                          </TableCell>
                          <TableCell className="text-sm">
                            {formatMoment(credential.expires_at)}
                          </TableCell>
                          <TableCell className="text-sm">
                            {formatMoment(credential.last_used_at)}
                          </TableCell>
                          <TableCell>
                            <StatusBadge
                              active={active}
                              activeLabel="Active"
                              inactiveLabel="Revoked"
                            />
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={!active}
                              onClick={() =>
                                setConfirm({
                                  title: `Revoke credential ${credential.id}?`,
                                  description:
                                    "Any automation still using this secret stops working immediately.",
                                  label: "Revoke credential",
                                  run: () => api.revokeClientCredential(selected.id, credential.id),
                                })
                              }
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
          </div>
        </Panel>
      ) : null}

      {/* Issue credential */}
      <Dialog open={issueFor !== null} onOpenChange={(open) => (open ? null : setIssueFor(null))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Issue credential for {issueFor?.name}</DialogTitle>
            <DialogDescription>
              The secret is displayed once and cannot be recovered afterwards.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitCredential} className="space-y-4" noValidate>
            <Field
              label="Expires in (days)"
              id="credential-days"
              error={credentialForm.formState.errors.expires_in_days?.message}
            >
              <Input
                id="credential-days"
                type="number"
                min={1}
                max={3650}
                {...credentialForm.register("expires_in_days")}
              />
            </Field>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setIssueFor(null)}>
                Cancel
              </Button>
              <Button type="submit">Issue credential</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* One-time credential display */}
      <Dialog
        open={issued !== null}
        onOpenChange={(open) => {
          if (!open) {
            setIssued(null);
            setCopied(false);
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-warning" aria-hidden />
              Copy this credential now
            </DialogTitle>
            <DialogDescription>
              {issued?.warning ??
                `This is the only time the secret for ${issued?.client ?? "this client"} is shown. Store it in your secret manager before closing.`}
            </DialogDescription>
          </DialogHeader>
          <p className="break-all rounded-md border border-border bg-muted/50 p-3 font-mono text-sm">
            {issued?.value}
          </p>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={async () => {
                if (!issued) return;
                try {
                  await navigator.clipboard.writeText(issued.value);
                  setCopied(true);
                } catch {
                  toast.error("Copying failed. Select the value and copy it manually.");
                }
              }}
            >
              {copied ? (
                <Check className="size-4" aria-hidden />
              ) : (
                <Copy className="size-4" aria-hidden />
              )}
              {copied ? "Copied" : "Copy credential"}
            </Button>
            <Button
              onClick={() => {
                setIssued(null);
                setCopied(false);
              }}
            >
              I have stored it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Grant portal to client */}
      <Dialog open={grantFor !== null} onOpenChange={(open) => (open ? null : setGrantFor(null))}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Grant portal access to {grantFor?.name}</DialogTitle>
            <DialogDescription>
              Use 0 days for access that never expires (maximum 3650).
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submitGrant} className="space-y-4" noValidate>
            <Field
              label="Portal"
              id="client-grant-portal"
              error={grantForm.formState.errors.portal_name?.message}
            >
              <Select
                value={grantForm.watch("portal_name")}
                onValueChange={(value) => grantForm.setValue("portal_name", value)}
              >
                <SelectTrigger id="client-grant-portal">
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
              id="client-grant-days"
              error={grantForm.formState.errors.expires_in_days?.message}
            >
              <Input
                id="client-grant-days"
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

      <p className="text-xs text-muted-foreground">
        The backend exposes no listing or per-grant revocation for client portal access, so granted
        portals are not shown per client. Revoking the whole client removes all of its access.
      </p>

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
