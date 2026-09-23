import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Eye, EyeOff, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { revealOtp } from "@/lib/api/endpoints";
import { errorMessage, isApiError } from "@/lib/api/client";
import type { OtpResponse, PortalSummary } from "@/lib/api/types";

interface LiveOtp {
  code: string;
  /** Server-clock expiry, seconds. */
  expiresAt: number;
  /** serverTime - clientTime at issue, used to correct clock drift. */
  skew: number;
  period: number;
}

/**
 * Codes start hidden. An OTP is requested only on an explicit Reveal, held in
 * component memory only (never in a query cache, storage, or the URL), and
 * cleared on expiry, page hide, unmount, or error.
 */
export function OtpCard({ portal }: { portal: PortalSummary }) {
  const [otp, setOtp] = useState<LiveOtp | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [expiredNotice, setExpiredNotice] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setOtp(null);
    setRemaining(0);
    setCopied(false);
  }, []);

  // Clear on navigation away / unmount.
  useEffect(() => clear, [clear]);

  // Clear when the page is hidden (tab switch, minimise, background).
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        clear();
        setError(null);
        setExpiredNotice(false);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [clear]);

  // Countdown against the server clock; no automatic re-reveal on expiry.
  useEffect(() => {
    if (!otp) return;
    const tick = () => {
      const nowServer = Date.now() / 1000 + otp.skew;
      const left = Math.max(0, Math.round(otp.expiresAt - nowServer));
      setRemaining(left);
      if (left <= 0) {
        clear();
        setExpiredNotice(true);
      }
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [otp, clear]);

  const reveal = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setExpiredNotice(false);
    try {
      const result: OtpResponse = await revealOtp(portal.portal_name, controller.signal);
      // Ignore a response that lands after hiding or navigating away.
      if (controller.signal.aborted || document.visibilityState === "hidden") return;
      setOtp({
        code: result.otp,
        expiresAt: result.expires_at,
        skew: result.server_time - Date.now() / 1000,
        period: result.period,
      });
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (isApiError(caught) && caught.kind === "gone") {
        setError("This portal's code endpoint is no longer available. Contact an administrator.");
      } else {
        setError(errorMessage(caught));
      }
    } finally {
      setLoading(false);
    }
  }, [portal.portal_name]);

  const copy = useCallback(async () => {
    if (!otp) return;
    try {
      await navigator.clipboard.writeText(otp.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copying failed. Select the code and copy it manually.");
    }
  }, [otp]);

  const progress = otp && otp.period > 0 ? Math.min(100, (remaining / otp.period) * 100) : 0;

  return (
    <article className="flex flex-col rounded-lg border border-border bg-card p-5 shadow-xs">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{portal.display_name}</h2>
          <p className="truncate font-mono text-xs text-muted-foreground">{portal.portal_name}</p>
        </div>
        <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
          {portal.period}s
        </span>
      </div>

      <div className="mt-5 flex min-h-20 items-center justify-center rounded-md border border-border bg-muted/40 px-4 py-4">
        {otp ? (
          <p
            className="otp-digits text-3xl text-foreground"
            aria-label={`One-time code ${otp.code.split("").join(" ")}`}
          >
            {otp.code}
          </p>
        ) : (
          <p className="otp-digits select-none text-3xl text-muted-foreground/45" aria-hidden>
            ••••••
          </p>
        )}
      </div>

      {otp ? (
        <div className="mt-3 space-y-1.5">
          <Progress value={progress} className="h-1" aria-hidden />
          <p className="text-xs text-muted-foreground" aria-hidden>
            Expires in {remaining}s
          </p>
          <span className="sr-only" aria-live="polite">
            Code revealed. It expires shortly.
          </span>
        </div>
      ) : null}

      {expiredNotice && !otp ? (
        <p className="mt-3 text-xs text-muted-foreground" role="status">
          The code expired and was cleared. Reveal again if you still need it.
        </p>
      ) : null}

      {error ? (
        <p className="mt-3 text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      <div className="mt-4 flex gap-2">
        {otp ? (
          <>
            <Button variant="outline" size="sm" className="flex-1" onClick={clear}>
              <EyeOff className="size-4" aria-hidden />
              Hide
            </Button>
            <Button size="sm" className="flex-1" onClick={() => void copy()}>
              {copied ? (
                <Check className="size-4" aria-hidden />
              ) : (
                <Copy className="size-4" aria-hidden />
              )}
              {copied ? "Copied" : "Copy"}
            </Button>
          </>
        ) : (
          <Button size="sm" className="flex-1" onClick={() => void reveal()} disabled={loading}>
            {loading ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : expiredNotice ? (
              <RefreshCw className="size-4" aria-hidden />
            ) : (
              <Eye className="size-4" aria-hidden />
            )}
            {loading ? "Requesting…" : expiredNotice ? "Reveal again" : "Reveal code"}
          </Button>
        )}
      </div>
    </article>
  );
}
