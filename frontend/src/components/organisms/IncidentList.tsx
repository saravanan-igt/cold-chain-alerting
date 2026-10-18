import Form from "react-bootstrap/Form";
import type { Incident, LifecycleFilter } from "@/types/domain";
import { Panel } from "@/components/molecules/Panel";
import { Pagination } from "@/components/molecules/Pagination";
import { IncidentRow } from "@/components/molecules/IncidentRow";
import { EmptyState } from "@/components/molecules/EmptyState";
import { QueryFeedback } from "@/components/molecules/QueryFeedback";

export interface IncidentListProps {
  items?: Incident[];
  lifecycle: LifecycleFilter;
  offset: number;
  pageSize: number;
  busy: boolean;
  error?: string;
  onRetry: () => void;
  onFilter: (value: LifecycleFilter) => void;
  onPage: (offset: number) => void;
  onSelect: (id: string) => void;
}
export function IncidentList(props: IncidentListProps) {
  const {
    items,
    lifecycle,
    offset,
    pageSize,
    busy,
    error,
    onRetry,
    onFilter,
    onPage,
    onSelect,
  } = props;
  return (
    <Panel
      id="incidents"
      title="Incident history"
      description="Every opening decision, with its original rule and supporting evidence"
      action={
        <Form.Select
          aria-label="Filter incident lifecycle"
          value={lifecycle}
          onChange={(event) => onFilter(event.target.value as LifecycleFilter)}
        >
          <option value="">All lifecycles</option>
          <option value="open">Open</option>
          <option value="recovered">Recovered</option>
        </Form.Select>
      }
    >
      <QueryFeedback loading={!items && busy} error={error} onRetry={onRetry} />
      {items?.map((incident) => (
        <IncidentRow
          key={incident.id}
          incident={incident}
          onSelect={onSelect}
        />
      ))}
      {items?.length === 0 && !error && (
        <EmptyState
          title="No incidents in this view"
          description="Only sustained, observed excursions create an incident."
        />
      )}
      <Pagination
        offset={offset}
        count={items?.length ?? 0}
        pageSize={pageSize}
        busy={busy || !!error}
        onChange={onPage}
      />
    </Panel>
  );
}
