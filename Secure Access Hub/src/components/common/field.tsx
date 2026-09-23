import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";

export function Field({
  label,
  id,
  error,
  children,
  hint,
}: {
  label: string;
  id: string;
  error?: string | undefined;
  children: ReactNode;
  hint?: string | undefined;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
