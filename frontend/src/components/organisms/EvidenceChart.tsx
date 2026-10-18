import type { Evidence, IncidentDetail } from "@/types/domain";
import { time } from "@/lib/format";
import styles from "./EvidenceChart.module.scss";

export function EvidenceChart({ detail }: { detail: IncidentDetail }) {
  const rows = detail.evidence;
  if (!rows.length) return <p>No evidence on this page.</p>;
  const start = new Date(rows[0].timestamp).getTime();
  const span = Math.max(1, new Date(rows.at(-1)!.timestamp).getTime() - start);
  const low =
    Math.min(detail.rule.threshold_c, ...rows.map((row) => row.temperature_c)) -
    1;
  const high =
    Math.max(detail.rule.threshold_c, ...rows.map((row) => row.temperature_c)) +
    1;
  const x = (row: Evidence) =>
    40 + ((new Date(row.timestamp).getTime() - start) / span) * 600;
  const y = (temperature: number) =>
    155 - ((temperature - low) / (high - low)) * 130;
  return (
    <svg
      className={styles.chart}
      viewBox="0 0 680 190"
      role="img"
      aria-label="Temperature evidence chart; exact observations are in the table below"
    >
      <rect
        x="40"
        y="20"
        width="600"
        height={Math.max(0, y(detail.rule.threshold_c) - 20)}
        fill="#fff0e9"
      />
      <line
        x1="40"
        x2="640"
        y1={y(detail.rule.threshold_c)}
        y2={y(detail.rule.threshold_c)}
        stroke="#bd6d40"
        strokeDasharray="5 5"
      />
      <text x="2" y={y(detail.rule.threshold_c) + 4} fontSize="11">
        {detail.rule.threshold_c} °C
      </text>
      {rows.map((row, index) => (
        <g key={row.timestamp}>
          {index > 0 &&
            new Date(row.timestamp).getTime() -
              new Date(rows[index - 1].timestamp).getTime() <=
              detail.rule.max_gap_minutes * 60000 && (
              <line
                data-testid="evidence-segment"
                x1={x(rows[index - 1])}
                y1={y(rows[index - 1].temperature_c)}
                x2={x(row)}
                y2={y(row.temperature_c)}
                stroke="#17675e"
                strokeWidth="2"
              />
            )}
          <circle
            cx={x(row)}
            cy={y(row.temperature_c)}
            r={row.timestamp === detail.qualified_at ? 6 : 4}
            fill={row.timestamp === detail.qualified_at ? "#b64a25" : "#17675e"}
          >
            <title>
              {time(row.timestamp)} UTC: {row.temperature_c} °C
              {row.timestamp === detail.qualified_at ? " · qualified" : ""}
            </title>
          </circle>
        </g>
      ))}
      <text x="40" y="182" fontSize="12">
        {time(rows[0].timestamp)}
      </text>
      <text x="600" y="182" fontSize="12">
        {time(rows.at(-1)!.timestamp)}
      </text>
    </svg>
  );
}
