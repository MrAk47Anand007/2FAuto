import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/features/auth/auth-context";
import { errorMessage, isApiError } from "@/lib/api/client";

export const Route = createFileRoute("/login")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Sign in — 2FAuto" },
      {
        name: "description",
        content: "Sign in to 2FAuto to access your authorized shared one-time codes.",
      },
      { property: "og:title", content: "Sign in — 2FAuto" },
      {
        property: "og:description",
        content: "Sign in to access your authorized shared one-time codes.",
      },
    ],
  }),
  component: LoginPage,
});

const schema = z.object({
  username: z.string().min(1, "Enter your username"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

function LoginPage() {
  const { signIn, status } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "" },
  });

  useEffect(() => {
    if (status === "authenticated") void navigate({ to: "/app/portals", replace: true });
  }, [status, navigate]);

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await signIn(values.username, values.password);
      await navigate({ to: "/app/portals", replace: true });
    } catch (error) {
      if (isApiError(error) && error.kind === "unauthenticated") {
        setFormError("Incorrect username or password, or too many recent attempts.");
      } else if (isApiError(error) && error.kind === "throttled") {
        setFormError(
          error.retryAfterSeconds
            ? `Too many attempts. Try again in ${error.retryAfterSeconds} seconds.`
            : "Too many attempts. Wait a moment and try again.",
        );
      } else {
        setFormError(errorMessage(error));
      }
    } finally {
      form.setValue("password", "");
    }
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex size-11 items-center justify-center rounded-lg bg-primary">
            <ShieldCheck className="size-5 text-primary-foreground" aria-hidden />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Sign in to 2FAuto</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Shared one-time codes, issued per user and fully audited.
            </p>
          </div>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-5 rounded-lg border border-border bg-card p-6 shadow-xs"
          noValidate
        >
          {formError ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {formError}
            </p>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              autoComplete="username"
              autoFocus
              aria-invalid={Boolean(form.formState.errors.username)}
              {...form.register("username")}
            />
            {form.formState.errors.username ? (
              <p className="text-sm text-destructive">{form.formState.errors.username.message}</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              aria-invalid={Boolean(form.formState.errors.password)}
              {...form.register("password")}
            />
            {form.formState.errors.password ? (
              <p className="text-sm text-destructive">{form.formState.errors.password.message}</p>
            ) : null}
          </div>

          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Access is granted by an administrator. There is no self-service sign-up or password reset.
        </p>
      </div>
    </div>
  );
}
