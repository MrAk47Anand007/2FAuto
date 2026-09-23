import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/common/states";
import { OtpCard } from "@/features/portals/otp-card";
import { listMyPortals } from "@/lib/api/endpoints";

export const Route = createFileRoute("/app/portals")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "My Portals — 2FAuto" },
      {
        name: "description",
        content: "Reveal one-time codes for the portals you are authorized to use.",
      },
      { property: "og:title", content: "My Portals — 2FAuto" },
      { property: "og:description", content: "Reveal one-time codes for your authorized portals." },
    ],
  }),
  component: MyPortalsPage,
});

function MyPortalsPage() {
  const [term, setTerm] = useState("");
  const query = useQuery({
    queryKey: ["ui", "portals"],
    queryFn: listMyPortals,
    staleTime: 60_000,
  });

  const portals = useMemo(() => {
    const all = query.data?.portals ?? [];
    const needle = term.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      (portal) =>
        portal.display_name.toLowerCase().includes(needle) ||
        portal.portal_name.toLowerCase().includes(needle),
    );
  }, [query.data, term]);

  return (
    <>
      <PageHeader
        title="My Portals"
        description="Codes stay hidden until you reveal them. Each reveal is recorded in the audit log."
      />

      <div className="relative max-w-sm">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Search your portals"
          aria-label="Search your portals"
          className="pl-9"
        />
      </div>

      {query.isPending ? (
        <Panel>
          <LoadingState rows={3} label="Loading your portals" />
        </Panel>
      ) : query.isError ? (
        <Panel>
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        </Panel>
      ) : portals.length === 0 ? (
        <Panel>
          <EmptyState
            title={term ? "No portals match your search" : "No portals assigned yet"}
            description={
              term
                ? "Try a different name. Search filters only the portals you can already access."
                : "An administrator must grant you access, directly or through a team."
            }
          />
        </Panel>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {portals.map((portal) => (
            <OtpCard key={portal.portal_name} portal={portal} />
          ))}
        </div>
      )}
    </>
  );
}
