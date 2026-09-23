import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, BookOpen, KeyRound, ShieldCheck } from "lucide-react";
import { PageHeader, Panel } from "@/components/common/states";
import { useAuth } from "@/features/auth/auth-context";

export const Route = createFileRoute("/app/api-guide")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "API Guide — 2FAuto" },
      {
        name: "description",
        content: "Request a portal TOTP with a scoped 2FAuto automation client credential.",
      },
    ],
  }),
  component: ApiGuidePage,
});

function ApiGuidePage() {
  const { isAdmin } = useAuth();
  const origin = typeof window === "undefined" ? "https://your-2fauto-host" : window.location.origin;
  const endpoint = "/api/v1/portals/{portal_name}/otp";

  return (
    <>
      <PageHeader
        title="API Guide"
        description="For scripts and bots that need a current code from a portal they are allowed to use."
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,1fr)]">
        <Panel className="p-5 sm:p-6">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <KeyRound className="size-4 text-primary" aria-hidden />
            Request a code
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            Send an HTTP <code className="font-mono text-foreground">POST</code> request with a
            scoped client credential. There is no request body.
          </p>
          <div className="mt-4 rounded-md border border-border bg-muted/40 px-4 py-3 font-mono text-xs break-all sm:text-sm">
            POST {endpoint}
          </div>
          <p className="mt-4 text-sm text-muted-foreground">
            Replace <code className="font-mono text-foreground">{"{portal_name}"}</code> with
            the portal route name shown on its card, such as <code className="font-mono text-foreground">bank-portal</code>.
          </p>
        </Panel>

        <Panel className="p-5 sm:p-6">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <ShieldCheck className="size-4 text-primary" aria-hidden />
            Before calling the API
          </div>
          <ol className="mt-4 list-decimal space-y-3 pl-5 text-sm text-muted-foreground">
            <li>An admin creates an automation client.</li>
            <li>The admin grants that client access to the required portal.</li>
            <li>The admin issues a credential and stores its one-time value in the bot&apos;s secure credential store.</li>
          </ol>
          {isAdmin ? (
            <Link
              to="/app/admin/clients"
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              Open Automation Clients <ArrowRight className="size-4" aria-hidden />
            </Link>
          ) : (
            <p className="mt-5 text-sm text-muted-foreground">Ask an administrator for client access.</p>
          )}
        </Panel>
      </div>

      <Panel className="p-5 sm:p-6">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <BookOpen className="size-4 text-primary" aria-hidden />
          Example request
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          PowerShell example: use the same base URL as this portal. Replace the example portal name
          and token placeholder. On macOS or Linux, use <code className="font-mono text-foreground">curl</code> instead of <code className="font-mono text-foreground">curl.exe</code>.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-md bg-sidebar p-4 text-xs leading-6 text-sidebar-foreground sm:text-sm"><code>{`curl.exe -X POST "${origin}/api/v1/portals/bank-portal/otp" -H "Authorization: Bearer <client-token>"`}</code></pre>
        <p className="mt-4 text-sm text-muted-foreground">A successful response looks like this:</p>
        <pre className="mt-3 overflow-x-auto rounded-md border border-border bg-muted/40 p-4 text-xs leading-6 sm:text-sm"><code>{`{
  "otp": "012345",
  "valid_for_seconds": 18,
  "period": 30,
  "timestamp": 1700000012,
  "portal_name": "bank-portal",
  "display_name": "Bank Portal"
}`}</code></pre>
        <p className="mt-4 text-sm text-muted-foreground">
          Keep <code className="font-mono text-foreground">otp</code> as text because a code can
          start with zero. Request a fresh code when its validity window is nearly over. A missing,
          invalid, or expired credential returns 401; an unavailable or ungranted portal returns 404;
          rate limiting returns 429.
        </p>
      </Panel>

      <Panel className="p-5 sm:p-6">
        <h2 className="text-sm font-semibold">Using the browser instead?</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          <Link to="/app/portals" className="font-medium text-primary hover:underline">My Portals</Link>
          {" "}uses <code className="font-mono text-foreground">POST /api/ui/portals/{"{portal_name}"}/otp</code>
          {" "}when you select <strong className="font-medium text-foreground">Reveal code</strong>.
          That browser endpoint requires your signed-in session and a CSRF token; use the scoped
          client endpoint above for automation. The legacy <code className="font-mono text-foreground">/otp</code> API is disabled by default.
        </p>
      </Panel>
    </>
  );
}
