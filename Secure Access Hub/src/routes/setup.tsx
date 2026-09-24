import { useEffect, useState, type FormEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/setup")({
  ssr: false,
  head: () => ({ meta: [{ title: "Set up 2FAuto" }] }),
  component: SetupPage,
});

type SetupStatus = { configured: boolean; setup_token?: string };

function SetupPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    void fetch("/api/setup/status", { cache: "no-store", credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Setup is available only on a local 2FAuto installation.");
        return (await response.json()) as SetupStatus;
      })
      .then((status) => {
        if (!active) return;
        if (status.configured) {
          void navigate({ to: "/login", replace: true });
          return;
        }
        setToken(status.setup_token ?? null);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Could not check setup status.");
        setLoading(false);
      });
    return () => { active = false; };
  }, [navigate]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!token) return setError("Setup is not ready. Reload this page and try again.");
    if (username.trim().length < 3) return setError("Enter a username with at least 3 characters.");
    if (password.length < 12) return setError("Use a password with at least 12 characters.");
    if (password !== confirmation) return setError("The passwords do not match.");
    setSubmitting(true);
    try {
      const response = await fetch("/api/setup/initialize", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Setup-Token": token },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (!response.ok) throw new Error(
        response.status === 409
          ? "This vault is already set up or needs its original recovery key."
          : "Setup could not finish. Check the username and password, then try again.",
      );
      setPassword("");
      setConfirmation("");
      await navigate({ to: "/login", replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Setup could not finish.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex size-11 items-center justify-center rounded-lg bg-primary">
            <ShieldCheck className="size-5 text-primary-foreground" aria-hidden />
          </div>
          <h1 className="text-lg font-semibold tracking-tight">Set up 2FAuto</h1>
          <p className="text-sm text-muted-foreground">
            Create the first administrator. Your vault keys are generated on this computer.
          </p>
        </div>
        {loading ? <p role="status" className="text-center text-sm">Checking installation…</p> : null}
        {error ? <p role="alert" className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p> : null}
        {!loading && token ? (
          <form onSubmit={(event) => void submit(event)} className="space-y-5 rounded-lg border border-border bg-card p-6 shadow-xs">
            <div className="space-y-2">
              <Label htmlFor="setup-username">Administrator username</Label>
              <Input id="setup-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={64} autoFocus />
            </div>
            <div className="space-y-2">
              <Label htmlFor="setup-password">Password</Label>
              <Input id="setup-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={12} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="setup-confirm">Confirm password</Label>
              <Input id="setup-confirm" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required minLength={12} />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Creating vault…" : "Create vault"}
            </Button>
          </form>
        ) : null}
      </div>
    </main>
  );
}
