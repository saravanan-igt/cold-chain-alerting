"use client";
import { useState } from "react";
import type { IncidentDetail } from "@/types/domain";
import { Timestamp } from "@/components/atoms/Timestamp";
import styles from "./IncidentResponsePanel.module.scss";

const EVENT_LABELS: Record<string, string> = {
  opened: "Incident opened by detector",
  recovered: "Recovery confirmed by detector",
  acknowledged: "Acknowledged",
  escalated: "Escalated — still unacknowledged",
};

export function IncidentResponsePanel({
  detail,
  acknowledging,
  error,
  onAcknowledge,
}: {
  detail: IncidentDetail;
  acknowledging: boolean;
  error?: string;
  onAcknowledge: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const ack = detail.acknowledgement;
  const timeline = detail.timeline ?? [];
  const deliveries = detail.notifications ?? [];
  return (
    <section className={styles.panel} aria-labelledby="response-heading">
      <h3 id="response-heading">Response ownership</h3>
      {ack ? (
        <p className={styles.acknowledged} role="status">
          <strong>Acknowledged by {ack.acknowledged_by}</strong> at{" "}
          <Timestamp value={ack.acknowledged_at} />
          {ack.note && <span className={styles.note}>“{ack.note}”</span>}
        </p>
      ) : (
        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            onAcknowledge(note.trim());
          }}
        >
          <p className={styles.awaiting}>
            Not yet acknowledged.
            {detail.lifecycle === "open" &&
              " Escalation continues until a named operator takes ownership."}
          </p>
          <label htmlFor="ack-note">Note for the audit trail (optional)</label>
          <input
            id="ack-note"
            maxLength={500}
            value={note}
            placeholder="e.g. Driver contacted; checking reefer unit"
            onChange={(event) => setNote(event.target.value)}
          />
          <button type="submit" disabled={acknowledging}>
            {acknowledging ? "Acknowledging…" : "Acknowledge incident"}
          </button>
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
        </form>
      )}

      {timeline.length > 0 && (
        <>
          <h4>Audit timeline</h4>
          <ol className={styles.timeline}>
            {timeline.map((item, index) => (
              <li key={`${item.kind}-${index}`}>
                <Timestamp value={item.at} /> ·{" "}
                {EVENT_LABELS[item.kind] ?? item.kind}
                {item.kind === "escalated" &&
                  typeof item.details.level_index === "number" &&
                  ` (level ${item.details.level_index + 1})`}{" "}
                <span className={styles.actor}>by {item.actor}</span>
              </li>
            ))}
          </ol>
        </>
      )}

      <h4>Notification deliveries</h4>
      {deliveries.length ? (
        <ul className={styles.deliveries}>
          {deliveries.map((item) => (
            <li key={item.id}>
              <span className={`${styles.delivery} ${styles[item.status]}`}>
                {item.status}
              </span>
              {item.event.replace("incident.", "")} → {item.channel_id}
              {item.attempts > 1 && ` · ${item.attempts} attempts`}
              {item.last_error && (
                <span className={styles.actor}> · {item.last_error}</span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.actor}>
          No notification channels are configured for these events.
        </p>
      )}
    </section>
  );
}
