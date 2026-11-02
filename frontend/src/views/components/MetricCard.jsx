export function MetricCard({ label, value, detail, icon, compact = false }) {
  return (
    <article className={`metric-card${compact ? " metric-card--compact" : ""}`}>
      {icon ? <span className="metric-card__symbol">{icon}</span> : null}
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
      {detail ? <p className="metric-card__detail">{detail}</p> : null}
    </article>
  );
}
