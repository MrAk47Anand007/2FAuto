import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  formatMoment,
} from "@/components/common/states";
import { listAuditEvents } from "@/lib/api/endpoints";

export const Route = createFileRoute("/app/admin/audit")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Audit Events — 2FAuto admin" },
      {
        name: "description",
        content: "Review the most recent security and access events recorded by 2FAuto.",
      },
      { property: "og:title", content: "Audit Events — 2FAuto admin" },
      {
        property: "og:description",
        content: "Recent security and access events recorded by 2FAuto.",
      },
    ],
  }),
  component: AuditPage,
});

const LIMITS = ["50", "100", "250", "500"] as const;

function AuditPage() {
  const [limit, setLimit] = useState<string>("100");
  const [term, setTerm] = useState("");

  const query = useQuery({
    queryKey: ["admin", "audit", limit],
    queryFn: () => listAuditEvents(Number(limit)),
  });

  const events = useMemo(() => {
    const all = query.data?.events ?? [];
    const needle = term.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((event) =>
      [
        event.action,
        event.actor_kind,
        event.actor_user_id,
        event.target_type,
        event.target_id,
        event.result,
        event.reason,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(needle)),
    );
  }, [query.data, term]);

  return (
    <>
      <PageHeader
        title="Audit Events"
        description="The most recent recorded events. Filtering below searches only the events already loaded, not the full history."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            <RefreshCw
              className={query.isFetching ? "size-4 animate-spin" : "size-4"}
              aria-hidden
            />
            Refresh
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-56 flex-1 max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="Filter loaded events"
            aria-label="Filter loaded events"
            className="pl-9"
          />
        </div>
        <Select value={limit} onValueChange={setLimit}>
          <SelectTrigger className="w-40" aria-label="Number of events to load">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LIMITS.map((value) => (
              <SelectItem key={value} value={value}>
                Load {value} events
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Panel>
        {query.isPending ? (
          <LoadingState rows={6} label="Loading audit events" />
        ) : query.isError ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : events.length === 0 ? (
          <EmptyState
            title={term ? "No loaded events match your filter" : "No events recorded"}
            description={term ? "Clear the filter or load more events." : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Event</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Target</TableHead>
                  <TableHead>Outcome</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {events.map((event) => (
                  <TableRow key={event.event_id}>
                    <TableCell className="whitespace-nowrap text-sm">
                      {formatMoment(event.created_at)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{event.action}</TableCell>
                    <TableCell className="text-sm">
                      {event.actor_user_id === null
                        ? event.actor_kind
                        : `${event.actor_kind} #${event.actor_user_id}`}
                    </TableCell>
                    <TableCell className="text-sm">
                      {event.target_id
                        ? `${event.target_type}: ${event.target_id}`
                        : event.target_type}
                    </TableCell>
                    <TableCell className="text-sm">{event.result}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>
    </>
  );
}
