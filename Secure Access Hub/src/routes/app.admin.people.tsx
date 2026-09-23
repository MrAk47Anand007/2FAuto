import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Search } from "lucide-react";
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
import { useAuth } from "@/features/auth/auth-context";
import * as api from "@/lib/api/endpoints";
import type { AdminUser } from "@/lib/api/types";

export const Route = createFileRoute("/app/admin/people")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "People — 2FAuto admin" },
      {
        name: "description",
        content: "Create accounts, set roles, and disable or reactivate 2FAuto users.",
      },
      { property: "og:title", content: "People — 2FAuto admin" },
      { property: "og:description", content: "Manage 2FAuto user accounts and roles." },
    ],
  }),
  component: PeoplePage,
});

const schema = z.object({
  username: z.string().min(2, "At least 2 characters"),
  password: z.string().min(8, "Use at least 8 characters"),
  role: z.enum(["admin", "user"]),
});
type Values = z.infer<typeof schema>;

function PeoplePage() {
  const queryClient = useQueryClient();
  const { user: me } = useAuth();
  const { perform, dialog } = useStepUpAction();
  const [term, setTerm] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [target, setTarget] = useState<AdminUser | null>(null);
  const [busy, setBusy] = useState(false);

  const query = useQuery({ queryKey: ["admin", "users"], queryFn: api.adminListUsers });
  const users = query.data?.users ?? [];

  const activeAdmins = users.filter((user) => user.role === "admin" && user.status !== "disabled");
  const isLastActiveAdmin = (user: AdminUser) =>
    user.role === "admin" && user.status !== "disabled" && activeAdmins.length <= 1;

  const filtered = useMemo(() => {
    const needle = term.trim().toLowerCase();
    if (!needle) return users;
    return users.filter((user) => user.username.toLowerCase().includes(needle));
  }, [users, term]);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", role: "user" },
  });

  const submit = form.handleSubmit(async (values) => {
    const ok = await perform("Create account", () => api.adminCreateUser(values));
    form.setValue("password", "");
    if (ok) {
      toast.success(`Account "${values.username}" created.`);
      form.reset({ username: "", password: "", role: "user" });
      setCreateOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    }
  });

  const toggleAccount = async () => {
    if (!target) return;
    const disabling = target.status !== "disabled";
    setBusy(true);
    const ok = await perform(disabling ? "Disable account" : "Reactivate account", () =>
      api.adminUserAction(target.username, disabling ? "disable" : "reactivate"),
    );
    setBusy(false);
    setTarget(null);
    if (ok) {
      toast.success(disabling ? "Account disabled." : "Account reactivated.");
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    }
  };

  return (
    <>
      <PageHeader
        title="People"
        description="Accounts that can sign in to 2FAuto. Disabling an account ends its access immediately."
        actions={
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="size-4" aria-hidden />
                New account
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Create account</DialogTitle>
                <DialogDescription>
                  Share the initial password through a secure channel. It is not shown again here.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submit} className="space-y-4" noValidate>
                <Field
                  label="Username"
                  id="new-username"
                  error={form.formState.errors.username?.message}
                >
                  <Input id="new-username" autoComplete="off" {...form.register("username")} />
                </Field>
                <Field
                  label="Initial password"
                  id="new-password"
                  error={form.formState.errors.password?.message}
                >
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    {...form.register("password")}
                  />
                </Field>
                <Field label="Role" id="new-role" error={form.formState.errors.role?.message}>
                  <Select
                    value={form.watch("role")}
                    onValueChange={(value) => form.setValue("role", value as Values["role"])}
                  >
                    <SelectTrigger id="new-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">User — portals and own sessions</SelectItem>
                      <SelectItem value="admin">Admin — full administration</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={form.formState.isSubmitting}>
                    Create account
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
          placeholder="Filter loaded accounts"
          aria-label="Filter loaded accounts"
          className="pl-9"
        />
      </div>

      <Panel>
        {query.isPending ? (
          <LoadingState label="Loading accounts" />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No accounts match"
            description="Adjust the filter or create an account."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last sign-in</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((user) => {
                  const disabled = user.status === "disabled";
                  const blocked = isLastActiveAdmin(user);
                  return (
                    <TableRow key={user.username}>
                      <TableCell className="text-sm font-medium">
                        {user.username}
                        {me?.username === user.username ? (
                          <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                        ) : null}
                      </TableCell>
                      <TableCell className="text-sm capitalize">{user.role}</TableCell>
                      <TableCell className="text-sm">{formatMoment(user.created_at)}</TableCell>
                      <TableCell className="text-sm">{formatMoment(user.last_login_at)}</TableCell>
                      <TableCell>
                        <StatusBadge active={!disabled} />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={blocked && !disabled}
                          title={
                            blocked && !disabled
                              ? "This is the only active administrator. Promote another admin first."
                              : undefined
                          }
                          onClick={() => setTarget(user)}
                        >
                          {disabled ? "Reactivate" : "Disable"}
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
        open={target !== null}
        onOpenChange={(open) => (open ? null : setTarget(null))}
        title={
          target?.status === "disabled"
            ? `Reactivate ${target?.username}?`
            : `Disable ${target?.username ?? "account"}?`
        }
        description={
          target?.status === "disabled"
            ? "The account can sign in again with its existing password and grants."
            : "All of this account's sessions end and it can no longer sign in. Grants are kept."
        }
        confirmLabel={target?.status === "disabled" ? "Reactivate" : "Disable"}
        destructive={target?.status !== "disabled"}
        busy={busy}
        onConfirm={() => void toggleAccount()}
      />

      {dialog}
    </>
  );
}
