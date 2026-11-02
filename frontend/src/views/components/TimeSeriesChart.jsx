import { useState } from "react";

function getTimestampMs(value) {
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatUtcAxisLabel(timestampMs) {
  return new Date(timestampMs).toISOString().slice(11, 19);
}

function buildPath(points, bounds, width, height, padding) {
  if (points.length === 0) {
    return "";
  }

  const timestampSpan = Math.max(bounds.maxTimestamp - bounds.minTimestamp, 1);
  const valueSpan = Math.max(bounds.maxValue - bounds.minValue, 1);
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;

  return points
    .map((point, index) => {
      const x =
        padding.left +
        ((point.timestampMs - bounds.minTimestamp) / timestampSpan) * innerWidth;
      const y =
        padding.top +
        innerHeight -
        ((point.value - bounds.minValue) / valueSpan) * innerHeight;

      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function normalizeSeries(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  return values
    .map((point) => {
      const timestampMs = getTimestampMs(point.timestamp);
      const value = Number(point.value);

      if (timestampMs === null || !Number.isFinite(value)) {
        return null;
      }

      return { timestampMs, value };
    })
    .filter(Boolean);
}

function createSeriesEntry({ label, unit, values, color }, index, palette) {
  const points = normalizeSeries(values);
  const maxPoint =
    points.length > 0
      ? points.reduce((currentMax, point) =>
          point.value > currentMax.value ? point : currentMax
        )
      : null;

  return {
    id: `${label}-${index}`,
    label,
    unit,
    color: color ?? palette[index % palette.length],
    points,
    maxPoint,
  };
}

function getChartPointCoordinates(point, bounds, width, height, padding) {
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const timestampSpan = Math.max(bounds.maxTimestamp - bounds.minTimestamp, 1);
  const valueSpan = Math.max(bounds.maxValue - bounds.minValue, 1);

  return {
    x:
      padding.left +
      ((point.timestampMs - bounds.minTimestamp) / timestampSpan) * innerWidth,
    y:
      padding.top +
      innerHeight -
      ((point.value - bounds.minValue) / valueSpan) * innerHeight,
  };
}

function getTimestampFromChartX(chartX, bounds, width, padding) {
  const innerWidth = width - padding.left - padding.right;
  const clampedX = Math.min(
    Math.max(chartX, padding.left),
    width - padding.right
  );
  const ratio = innerWidth > 0 ? (clampedX - padding.left) / innerWidth : 0;

  return bounds.minTimestamp + ratio * (bounds.maxTimestamp - bounds.minTimestamp);
}

function findNearestPoint(points, targetTimestampMs) {
  if (points.length === 0) {
    return null;
  }

  let nearestPoint = points[0];
  let nearestDelta = Math.abs(points[0].timestampMs - targetTimestampMs);

  for (let index = 1; index < points.length; index += 1) {
    const delta = Math.abs(points[index].timestampMs - targetTimestampMs);
    if (delta < nearestDelta) {
      nearestPoint = points[index];
      nearestDelta = delta;
    }
  }

  return nearestPoint;
}

export function TimeSeriesChart({ title, unit, values, series }) {
  const width = 920;
  const height = 280;
  const padding = { top: 24, right: 24, bottom: 42, left: 54 };
  const [hoverState, setHoverState] = useState(null);
  const palette = ["#0f766e", "#f08c3a", "#1f4f7a", "#b45309"];
  const normalizedSeries =
    Array.isArray(series) && series.length > 0
      ? series.map((entry, index) =>
          createSeriesEntry(
            {
              label: entry.label,
              unit: entry.unit ?? unit,
              values: entry.values,
              color: entry.color,
            },
            index,
            palette
          )
        )
      : [
          createSeriesEntry(
            {
              label: title,
              unit,
              values,
              color: palette[0],
            },
            0,
            palette
          ),
        ];
  const allPoints = normalizedSeries.flatMap((entry) => entry.points);
  const timestamps = allPoints.map((point) => point.timestampMs);
  const numericValues = allPoints.map((point) => point.value);
  const minTimestamp = timestamps.length > 0 ? Math.min(...timestamps) : null;
  const maxTimestamp = timestamps.length > 0 ? Math.max(...timestamps) : null;
  const minValue = numericValues.length > 0 ? Math.min(...numericValues) : null;
  const maxValue = numericValues.length > 0 ? Math.max(...numericValues) : null;
  const bounds =
    minTimestamp !== null &&
    maxTimestamp !== null &&
    minValue !== null &&
    maxValue !== null
      ? { minTimestamp, maxTimestamp, minValue, maxValue }
      : null;
  const renderableSeries = bounds
    ? normalizedSeries
        .map((entry) => ({
          ...entry,
          path:
            entry.points.length > 1
              ? buildPath(entry.points, bounds, width, height, padding)
              : "",
          marker:
            entry.maxPoint !== null
              ? getChartPointCoordinates(entry.maxPoint, bounds, width, height, padding)
              : null,
        }))
        .filter((entry) => entry.points.length > 0)
    : [];
  const hasChartData = renderableSeries.some((entry) => entry.points.length > 1);
  const hoverDetails =
    hoverState && bounds
      ? (() => {
          const timestampMs = getTimestampFromChartX(
            hoverState.chartX,
            bounds,
            width,
            padding
          );
          const seriesValues = renderableSeries
            .map((entry) => {
              const point = findNearestPoint(entry.points, timestampMs);
              if (!point) {
                return null;
              }

              return {
                id: entry.id,
                label: entry.label,
                unit: entry.unit,
                color: entry.color,
                point,
                coordinates: getChartPointCoordinates(
                  point,
                  bounds,
                  width,
                  height,
                  padding
                ),
              };
            })
            .filter(Boolean);

          if (seriesValues.length === 0) {
            return null;
          }

          const anchorTimestampMs = seriesValues[0].point.timestampMs;
          const guideX = seriesValues[0].coordinates.x;

          return {
            guideX,
            timestampMs: anchorTimestampMs,
            tooltipLeft: Math.min(Math.max(guideX + 14, 16), width - 220),
            tooltipTop: padding.top + 10,
            seriesValues,
          };
        })()
      : null;

  return (
    <article className="dashboard-panel time-series-chart">
      <div className="section-heading section-heading--stacked">
        <div>
          <p className="eyebrow">UTC chart</p>
          <h2>{title}</h2>
        </div>
        {renderableSeries.length > 0 && (
          <div className="time-series-chart__legend" aria-label={`${title} series`}>
            {renderableSeries.map((entry) => (
              <div key={entry.id} className="time-series-chart__legend-item">
                <span
                  className="time-series-chart__legend-swatch"
                  style={{ backgroundColor: entry.color }}
                  aria-hidden="true"
                />
                <strong>{entry.label}</strong>
                {entry.maxPoint && (
                  <span>
                    Top {entry.maxPoint.value.toFixed(1)}
                    {entry.unit ? ` ${entry.unit}` : ""}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {hasChartData && bounds ? (
        <svg
          className="time-series-chart__svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${title} over UTC time`}
          onMouseMove={(event) => {
            const boundsRect = event.currentTarget.getBoundingClientRect();
            if (boundsRect.width <= 0 || boundsRect.height <= 0) {
              return;
            }

            const relativeX =
              ((event.clientX - boundsRect.left) / boundsRect.width) * width;
            setHoverState({ chartX: relativeX });
          }}
          onMouseLeave={() => setHoverState(null)}
        >
          <line
            className="time-series-chart__axis"
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
          />
          <line
            className="time-series-chart__axis"
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={height - padding.bottom}
          />
          {hoverDetails && (
            <line
              className="time-series-chart__guide"
              x1={hoverDetails.guideX}
              y1={padding.top}
              x2={hoverDetails.guideX}
              y2={height - padding.bottom}
            />
          )}
          {renderableSeries.map((entry) =>
            entry.path ? (
              <path
                key={entry.id}
                className="time-series-chart__line"
                d={entry.path}
                style={{ stroke: entry.color }}
              />
            ) : null
          )}
          {hoverDetails?.seriesValues.map((entry) => (
            <circle
              key={`${entry.id}-hover`}
              className="time-series-chart__hover-dot"
              cx={entry.coordinates.x}
              cy={entry.coordinates.y}
              r="4"
              style={{ fill: entry.color }}
            />
          ))}
          {renderableSeries.map((entry) => {
            if (!entry.marker || !entry.maxPoint) {
              return null;
            }

            const labelX = Math.min(entry.marker.x + 10, width - padding.right - 84);
            const labelY = Math.max(entry.marker.y - 10, padding.top + 14);

            return (
              <g key={`${entry.id}-marker`} className="time-series-chart__peak-group">
                <circle
                  className="time-series-chart__peak-dot"
                  cx={entry.marker.x}
                  cy={entry.marker.y}
                  r="5"
                  style={{ fill: entry.color }}
                />
                <text
                  className="time-series-chart__peak-label"
                  x={labelX}
                  y={labelY}
                  style={{ fill: entry.color }}
                >
                  {entry.label}: {entry.maxPoint.value.toFixed(1)}
                  {entry.unit ? ` ${entry.unit}` : ""}
                </text>
              </g>
            );
          })}

          <text className="time-series-chart__tick" x={padding.left} y={height - 14}>
            {formatUtcAxisLabel(minTimestamp)}
          </text>
          <text
            className="time-series-chart__tick time-series-chart__tick--end"
            x={width - padding.right}
            y={height - 14}
          >
            {formatUtcAxisLabel(maxTimestamp)}
          </text>
          <text className="time-series-chart__tick" x={8} y={padding.top + 4}>
            {maxValue?.toFixed(1)}{unit ? ` ${unit}` : ""}
          </text>
          <text className="time-series-chart__tick" x={8} y={height - padding.bottom}>
            {minValue?.toFixed(1)}{unit ? ` ${unit}` : ""}
          </text>
          {hoverDetails && (
            <foreignObject
              x={hoverDetails.tooltipLeft}
              y={hoverDetails.tooltipTop}
              width="204"
              height={56 + hoverDetails.seriesValues.length * 22}
            >
              <div className="time-series-chart__tooltip">
                <strong>{formatUtcAxisLabel(hoverDetails.timestampMs)}</strong>
                {hoverDetails.seriesValues.map((entry) => (
                  <div
                    key={`${entry.id}-tooltip`}
                    className="time-series-chart__tooltip-row"
                  >
                    <span
                      className="time-series-chart__legend-swatch"
                      style={{ backgroundColor: entry.color }}
                      aria-hidden="true"
                    />
                    <span>{entry.label}</span>
                    <span>
                      {entry.point.value.toFixed(1)}
                      {entry.unit ? ` ${entry.unit}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            </foreignObject>
          )}
        </svg>
      ) : (
        <p className="time-series-chart__empty">No chart data is available.</p>
      )}
    </article>
  );
}
