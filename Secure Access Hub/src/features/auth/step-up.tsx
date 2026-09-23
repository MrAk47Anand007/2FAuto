import { useCallback, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stepUp } from "@/lib/api/endpoints";
import { errorMessage, isApiError, needsStepUp } from "@/lib/api/client";

const schema = z.object({ password: z.string().min(1, "Enter your password") });
type FormValues = z.infer<typeof schema>;

type PendingAction = { label: string; run: () => Promise<unknown> } | null;

/**
 * Runs sensitive admin actions. If the backend answers 428 (recent step-up
 * required) the password dialog opens. After a successful step-up the user
 * must deliberately confirm before the original action is resumed.
 */
export function useStepUpAction() {
  const [pending, setPending] = useState<PendingAction>(null);
  const [verified, setVerified] = useState(false);
  const [open, setOpen] = useState(false);
  const runningRef = useRef(false);

  const perform = useCallback(async (label: string, run: () => Promise<unknown>) => {
    try {
      await run();
      return true;
    } catch (error) {
      if (needsStepUp(error)) {
        setPending({ label, run });
        setVerified(false);
        setOpen(true);
        return false;
      }
      if (isApiError(error) && error.kind === "throttled" && error.retryAfterSeconds) {
        toast.error(`Too many attempts. Try again in ${error.retryAfterSeconds}s.`);
        return false;
      }
      toast.error(errorMessage(error));
      return false;
    }
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setPending(null);
    setVerified(false);
  }, []);

  const resume = useCallback(async () => {
    if (!pending || runningRef.current) return;
    runningRef.current = true;
    try {
      await pending.run();
      toast.success("Action completed.");
      close();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      runningRef.current = false;
    }
  }, [pending, close]);

  const dialog = (
    <StepUpDialog
      open={open}
      label={pending?.label ?? ""}
      verified={verified}
      onVerified={() => setVerified(true)}
      onResume={resume}
      onOpenChange={(next) => (next ? setOpen(true) : close())}
    />
  );

  return { perform, dialog };
}

function StepUpDialog({
  open,
  label,
  verified,
  onVerified,
  onResume,
  onOpenChange,
}: {
  open: boolean;
  label: string;
  verified: boolean;
  onVerified: () => void;
  onResume: () => void;
  onOpenChange: (open: boolean) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setSubmitting(true);
    try {
      await stepUp(values.password);
      onVerified();
    } catch (error) {
      if (isApiError(error) && error.kind === "throttled") {
        form.setError("password", {
          message: error.retryAfterSeconds
            ? `Too many attempts. Try again in ${error.retryAfterSeconds}s.`
            : "Too many attempts. Wait and try again.",
        });
      } else if (isApiError(error) && error.kind === "forbidden") {
        form.setError("password", { message: "That password is incorrect." });
      } else {
        form.setError("password", { message: errorMessage(error) });
      }
    } finally {
      // Never keep the entered password in memory.
      form.setValue("password", "");
      setSubmitting(false);
    }
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        form.reset({ password: "" });
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-accent" aria-hidden />
            Confirm your identity
          </DialogTitle>
          <DialogDescription>
            {verified
              ? "Verified for the next 5 minutes. Confirm to continue with the action you started."
              : "This is a sensitive action. Re-enter your password to continue."}
          </DialogDescription>
        </DialogHeader>

        {verified ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={onResume}>Continue: {label}</Button>
          </DialogFooter>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="step-up-password">Password</Label>
              <Input
                id="step-up-password"
                type="password"
                autoComplete="current-password"
                autoFocus
                aria-invalid={Boolean(form.formState.errors.password)}
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <p className="text-sm text-destructive" role="alert">
                  {form.formState.errors.password.message}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Verifying…" : "Verify"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
