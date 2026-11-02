function buildConicGradient(segments) {
  let cursor = 0;

  return `conic-gradient(${segments
    .map((segment) => {
      const start = cursor;
      cursor += segment.value;
      return `${segment.color} ${start}% ${cursor}%`;
    })
    .join(", ")})`;
}

export function RingChart({ chart }) {
  return (
    <article className="dashboard-panel ring-chart">
      <div className="section-heading section-heading--stacked">
        <div>
          <h2>{chart.title}</h2>
        </div>
      </div>

      <div className="ring-chart__layout">
        <div
          className="ring-chart__visual"
          style={{ backgroundImage: buildConicGradient(chart.segments) }}
          aria-label={chart.title}
        >
          <div className="ring-chart__center">
            <strong>{chart.centerValue}</strong>
            <span>{chart.subtitle}</span>
          </div>
        </div>
      </div>
    </article>
  );
}
