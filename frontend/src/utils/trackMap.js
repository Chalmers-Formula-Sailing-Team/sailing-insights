function toRadians(value) {
  return (value * Math.PI) / 180;
}

export function buildTrackPath(trackPoints) {
  return trackPoints
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
}

export function sampleTrackPoints(points, limit) {
  if (!Array.isArray(points) || points.length === 0) {
    return [];
  }

  if (!Number.isFinite(limit) || limit < 2 || points.length <= limit) {
    return points;
  }

  const step = (points.length - 1) / (limit - 1);
  return Array.from({ length: limit }, (_, index) => points[Math.round(index * step)]);
}

export function projectTrackPoints(trackPoints, options = {}) {
  if (!Array.isArray(trackPoints) || trackPoints.length === 0) {
    return [];
  }

  const mapSize = Number.isFinite(options.mapSize) ? options.mapSize : 100;
  const padding = Number.isFinite(options.padding) ? options.padding : 8;
  const innerSize = Math.max(mapSize - padding * 2, 0);
  const geographicPoints = trackPoints
    .map((point) => {
      const latitude = Number(point.latitude ?? point.lat);
      const longitude = Number(point.longitude ?? point.lon);

      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return null;
      }

      return {
        ...point,
        latitude,
        longitude,
      };
    })
    .filter(Boolean);

  if (geographicPoints.length === 0) {
    return [];
  }

  const meanLatitude =
    geographicPoints.reduce((sum, point) => sum + point.latitude, 0) /
    geographicPoints.length;
  const longitudeScale = Math.max(Math.cos(toRadians(meanLatitude)), 0.0001);
  const projectedPoints = geographicPoints.map((point) => ({
    ...point,
    projectedX: point.longitude * longitudeScale,
    projectedY: point.latitude,
  }));

  const projectedXValues = projectedPoints.map((point) => point.projectedX);
  const projectedYValues = projectedPoints.map((point) => point.projectedY);
  const minProjectedX = Math.min(...projectedXValues);
  const maxProjectedX = Math.max(...projectedXValues);
  const minProjectedY = Math.min(...projectedYValues);
  const maxProjectedY = Math.max(...projectedYValues);
  const spanX = maxProjectedX - minProjectedX;
  const spanY = maxProjectedY - minProjectedY;
  const scale = innerSize / Math.max(spanX, spanY, 0.000001);
  const offsetX = padding + (innerSize - spanX * scale) / 2;
  const offsetY = padding + (innerSize - spanY * scale) / 2;

  return projectedPoints.map((point) => ({
    ...point,
    x: Number((offsetX + (point.projectedX - minProjectedX) * scale).toFixed(2)),
    y: Number((mapSize - (offsetY + (point.projectedY - minProjectedY) * scale)).toFixed(2)),
  }));
}

export function formatCoordinate(value, positiveLabel, negativeLabel) {
  if (!Number.isFinite(value)) {
    return "";
  }

  const absoluteValue = Math.abs(value).toFixed(5);
  return `${absoluteValue}°${value >= 0 ? positiveLabel : negativeLabel}`;
}
