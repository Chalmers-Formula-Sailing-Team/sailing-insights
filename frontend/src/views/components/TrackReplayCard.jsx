import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { formatCoordinate } from "../../utils/trackMap.js";

const DEFAULT_MAP_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const DEFAULT_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const TRACK_BASE_COLOR = "#f6efe3";
const TRACK_FOILING_COLOR = "#2fb344";
const MANEUVER_TACK_COLOR = "#2dd4bf";
const MANEUVER_GYBE_COLOR = "#fb923c";
const MANEUVER_FOILING_RING_COLOR = "#f8d66d";
const ZOOM_BUTTON_STEP = 0.5;
const TURN_RATE_COLOR_STOPS = [
  { ratio: 0, color: "#2447a6" },
  { ratio: 0.2, color: "#4d7fe0" },
  { ratio: 0.4, color: "#a9c8ff" },
  { ratio: 0.5, color: "#f6efe3" },
  { ratio: 0.6, color: "#ffc1aa" },
  { ratio: 0.8, color: "#f46d43" },
  { ratio: 1, color: "#a50026" },
];
const SPEED_COLOR_STOPS = [
  { ratio: 0, color: "#000004" },
  { ratio: 0.12, color: "#160b39" },
  { ratio: 0.24, color: "#420a68" },
  { ratio: 0.38, color: "#6a176e" },
  { ratio: 0.52, color: "#932667" },
  { ratio: 0.68, color: "#bc3754" },
  { ratio: 0.82, color: "#ed6925" },
  { ratio: 0.92, color: "#fbb318" },
  { ratio: 1, color: "#fcffa4" },
];

function getMapTileUrl() {
  const tileUrl =
    typeof import.meta.env.VITE_MAP_TILE_URL === "string" &&
    import.meta.env.VITE_MAP_TILE_URL.trim()
      ? import.meta.env.VITE_MAP_TILE_URL.trim()
      : DEFAULT_MAP_TILE_URL;

  return tileUrl.replace("{s}.tile.", "tile.");
}

function getTileAttribution() {
  return typeof import.meta.env.VITE_MAP_TILE_ATTRIBUTION === "string" &&
    import.meta.env.VITE_MAP_TILE_ATTRIBUTION.trim()
    ? import.meta.env.VITE_MAP_TILE_ATTRIBUTION.trim()
    : DEFAULT_TILE_ATTRIBUTION;
}

function buildMapStyle(tileUrl, tileAttribution) {
  return {
    version: 8,
    sources: {
      "osm-raster": {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
        attribution: tileAttribution,
      },
    },
    layers: [
      {
        id: "osm-raster",
        type: "raster",
        source: "osm-raster",
      },
    ],
  };
}

function buildTrackFeatureCollection(coordinates) {
  return {
    type: "FeatureCollection",
    features:
      coordinates.length > 1
        ? [
            {
              type: "Feature",
              properties: {},
              geometry: {
                type: "LineString",
                coordinates,
              },
            },
          ]
        : [],
  };
}

function buildTrackFeature(coordinates, color = TRACK_BASE_COLOR) {
  return {
    type: "Feature",
    properties: { color },
    geometry: {
      type: "LineString",
      coordinates,
    },
  };
}

function buildTrackSegmentsFeatureCollection(features) {
  return {
    type: "FeatureCollection",
    features,
  };
}

function getTimestampMs(value) {
  if (!value) {
    return null;
  }

  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function getSampleToleranceMs(timestamps) {
  if (timestamps.length < 2) {
    return 750;
  }

  const gaps = [];
  for (let index = 1; index < timestamps.length; index += 1) {
    const gap = timestamps[index] - timestamps[index - 1];
    if (gap > 0) {
      gaps.push(gap);
    }
  }

  if (gaps.length === 0) {
    return 750;
  }

  gaps.sort((left, right) => left - right);
  const medianGap = gaps[Math.floor(gaps.length / 2)];
  return Math.max(750, medianGap * 1.5);
}

function findClosestTimestampIndex(timestamps, timestampMs) {
  if (!Array.isArray(timestamps) || timestamps.length === 0 || timestampMs === null) {
    return -1;
  }

  let low = 0;
  let high = timestamps.length - 1;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] < timestampMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }

  const currentTimestamp = timestamps[low];
  const previousIndex = Math.max(low - 1, 0);
  const previousTimestamp = timestamps[previousIndex];
  const currentDelta = Math.abs(currentTimestamp - timestampMs);
  const previousDelta = Math.abs(previousTimestamp - timestampMs);

  return previousDelta <= currentDelta ? previousIndex : low;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360;
}

function toNumericValue(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function toBooleanValue(value) {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value !== 0;
  }

  if (typeof value === "string") {
    const normalizedValue = value.trim().toLowerCase();
    if (normalizedValue === "true" || normalizedValue === "1" || normalizedValue === "yes") {
      return true;
    }

    if (
      normalizedValue === "false" ||
      normalizedValue === "0" ||
      normalizedValue === "no" ||
      normalizedValue === ""
    ) {
      return false;
    }
  }

  return Boolean(value);
}

function prepareTimedValueLookup(channel, valueMapper) {
  const values = Array.isArray(channel?.values) ? channel.values : [];
  const samples = values
    .map((value) => {
      const timestampMs = getTimestampMs(value?.timestamp);
      const mappedValue = valueMapper(value?.value);
      if (timestampMs === null) {
        return null;
      }

      if (mappedValue === null) {
        return null;
      }

      return {
        timestampMs,
        value: mappedValue,
      };
    })
    .filter(Boolean);

  return {
    samples,
    timestamps: samples.map((sample) => sample.timestampMs),
    sampleToleranceMs: getSampleToleranceMs(samples.map((sample) => sample.timestampMs)),
  };
}

function findTimedValueAtTime(lookup, timestampMs) {
  if (!lookup.samples.length || timestampMs === null) {
    return null;
  }

  const closestIndex = findClosestTimestampIndex(lookup.timestamps, timestampMs);
  if (closestIndex < 0) {
    return null;
  }

  const closestSample = lookup.samples[closestIndex];
  if (Math.abs(closestSample.timestampMs - timestampMs) > lookup.sampleToleranceMs) {
    return null;
  }

  return closestSample.value;
}

function prepareFoilingLookup(channel) {
  return prepareTimedValueLookup(channel, (value) => toBooleanValue(value));
}

function findFoilingStateAtTime(lookup, timestampMs) {
  return findTimedValueAtTime(lookup, timestampMs);
}

function prepareSpeedLookup(channel) {
  return prepareTimedValueLookup(channel, (value) => {
    const numericValue = toNumericValue(value);
    return numericValue === null ? null : Math.max(numericValue, 0);
  });
}

function findSpeedAtTime(lookup, timestampMs) {
  return findTimedValueAtTime(lookup, timestampMs);
}

function prepareRideHeightLookup(channel) {
  return prepareTimedValueLookup(channel, (value) => {
    const numericValue = toNumericValue(value);
    return numericValue === null ? null : numericValue;
  });
}

function findRideHeightAtTime(lookup, timestampMs) {
  return findTimedValueAtTime(lookup, timestampMs);
}

function prepareTurnRateLookup(channel) {
  return prepareTimedValueLookup(channel, (value) => toNumericValue(value));
}

function findTurnRateAtTime(lookup, timestampMs) {
  return findTimedValueAtTime(lookup, timestampMs);
}

function hexToRgb(hexColor) {
  const normalizedHex = hexColor.replace("#", "");
  const parsedHex =
    normalizedHex.length === 3
      ? normalizedHex
          .split("")
          .map((digit) => `${digit}${digit}`)
          .join("")
      : normalizedHex;

  return {
    red: Number.parseInt(parsedHex.slice(0, 2), 16),
    green: Number.parseInt(parsedHex.slice(2, 4), 16),
    blue: Number.parseInt(parsedHex.slice(4, 6), 16),
  };
}

function interpolateColor(startColor, endColor, ratio) {
  const start = hexToRgb(startColor);
  const end = hexToRgb(endColor);

  return `rgb(${Math.round(start.red + (end.red - start.red) * ratio)}, ${Math.round(
    start.green + (end.green - start.green) * ratio
  )}, ${Math.round(start.blue + (end.blue - start.blue) * ratio)})`;
}

function getSpeedColor(speed, range) {
  if (!range || !Number.isFinite(range.max) || range.max <= range.min) {
    return TRACK_BASE_COLOR;
  }

  const normalizedRatio = clamp(
    (Math.max(speed ?? 0, range.min) - range.min) / (range.max - range.min),
    0,
    1
  );
  const upperStopIndex = SPEED_COLOR_STOPS.findIndex(
    (stop) => normalizedRatio <= stop.ratio
  );

  if (upperStopIndex <= 0) {
    return SPEED_COLOR_STOPS[0].color;
  }

  if (upperStopIndex === -1) {
    return SPEED_COLOR_STOPS[SPEED_COLOR_STOPS.length - 1].color;
  }

  const lowerStop = SPEED_COLOR_STOPS[upperStopIndex - 1];
  const upperStop = SPEED_COLOR_STOPS[upperStopIndex];
  const stopSpan = upperStop.ratio - lowerStop.ratio || 1;
  const stopRatio = (normalizedRatio - lowerStop.ratio) / stopSpan;

  return interpolateColor(lowerStop.color, upperStop.color, stopRatio);
}

function getTurnRateColor(turnRate, range) {
  if (!range || !Number.isFinite(range.maxAbs) || range.maxAbs <= 0) {
    return TRACK_BASE_COLOR;
  }

  const normalizedRatio = clamp(
    ((clamp(turnRate ?? 0, -range.maxAbs, range.maxAbs) + range.maxAbs) /
      (2 * range.maxAbs)),
    0,
    1
  );
  const upperStopIndex = TURN_RATE_COLOR_STOPS.findIndex(
    (stop) => normalizedRatio <= stop.ratio
  );

  if (upperStopIndex <= 0) {
    return TURN_RATE_COLOR_STOPS[0].color;
  }

  if (upperStopIndex === -1) {
    return TURN_RATE_COLOR_STOPS[TURN_RATE_COLOR_STOPS.length - 1].color;
  }

  const lowerStop = TURN_RATE_COLOR_STOPS[upperStopIndex - 1];
  const upperStop = TURN_RATE_COLOR_STOPS[upperStopIndex];
  const stopSpan = upperStop.ratio - lowerStop.ratio || 1;
  const stopRatio = (normalizedRatio - lowerStop.ratio) / stopSpan;

  return interpolateColor(lowerStop.color, upperStop.color, stopRatio);
}

function buildSpeedTrackFeatureCollection(trackPoints, speedChannel, speedRange) {
  const coordinates = trackPoints.map((point) => [point.longitude, point.latitude]);
  if (coordinates.length < 2) {
    return buildTrackFeatureCollection(coordinates);
  }

  const speedLookup = prepareSpeedLookup(speedChannel);
  if (speedLookup.samples.length === 0) {
    return buildTrackSegmentsFeatureCollection([buildTrackFeature(coordinates)]);
  }

  const pointSpeeds = trackPoints.map((point) =>
    findSpeedAtTime(speedLookup, getTimestampMs(point?.timestamp))
  );
  const features = [];

  for (let index = 1; index < coordinates.length; index += 1) {
    const segmentCoordinates = [coordinates[index - 1], coordinates[index]];
    const startSpeed = pointSpeeds[index - 1];
    const endSpeed = pointSpeeds[index];
    const segmentSpeed =
      startSpeed !== null && endSpeed !== null
        ? (startSpeed + endSpeed) / 2
        : startSpeed ?? endSpeed ?? 0;

    features.push(
      buildTrackFeature(
        segmentCoordinates,
        getSpeedColor(segmentSpeed, speedRange)
      )
    );
  }

  return buildTrackSegmentsFeatureCollection(features);
}

function buildTurnRateTrackFeatureCollection(
  trackPoints,
  turnRateChannel,
  turnRateRange
) {
  const coordinates = trackPoints.map((point) => [point.longitude, point.latitude]);
  if (coordinates.length < 2) {
    return buildTrackFeatureCollection(coordinates);
  }

  const turnRateLookup = prepareTurnRateLookup(turnRateChannel);
  if (turnRateLookup.samples.length === 0) {
    return buildTrackSegmentsFeatureCollection([buildTrackFeature(coordinates)]);
  }

  const pointTurnRates = trackPoints.map((point) =>
    findTurnRateAtTime(turnRateLookup, getTimestampMs(point?.timestamp))
  );
  const features = [];

  for (let index = 1; index < coordinates.length; index += 1) {
    const segmentCoordinates = [coordinates[index - 1], coordinates[index]];
    const startTurnRate = pointTurnRates[index - 1];
    const endTurnRate = pointTurnRates[index];
    const segmentTurnRate =
      startTurnRate !== null && endTurnRate !== null
        ? (startTurnRate + endTurnRate) / 2
        : startTurnRate ?? endTurnRate ?? 0;

    features.push(
      buildTrackFeature(
        segmentCoordinates,
        getTurnRateColor(segmentTurnRate, turnRateRange)
      )
    );
  }

  return buildTrackSegmentsFeatureCollection(features);
}

function buildRideHeightTrackFeatureCollection(
  trackPoints,
  rideHeightChannel,
  rideHeightRange
) {
  const coordinates = trackPoints.map((point) => [point.longitude, point.latitude]);
  if (coordinates.length < 2) {
    return buildTrackFeatureCollection(coordinates);
  }

  const rideHeightLookup = prepareRideHeightLookup(rideHeightChannel);
  if (rideHeightLookup.samples.length === 0) {
    return buildTrackSegmentsFeatureCollection([buildTrackFeature(coordinates)]);
  }

  const pointHeights = trackPoints.map((point) =>
    findRideHeightAtTime(rideHeightLookup, getTimestampMs(point?.timestamp))
  );
  const features = [];

  for (let index = 1; index < coordinates.length; index += 1) {
    const segmentCoordinates = [coordinates[index - 1], coordinates[index]];
    const startHeight = pointHeights[index - 1];
    const endHeight = pointHeights[index];
    const segmentHeight =
      startHeight !== null && endHeight !== null
        ? (startHeight + endHeight) / 2
        : startHeight ?? endHeight ?? 0;

    features.push(
      buildTrackFeature(
        segmentCoordinates,
        getSpeedColor(segmentHeight, rideHeightRange)
      )
    );
  }

  return buildTrackSegmentsFeatureCollection(features);
}

function buildOverlayTrackFeatureCollection(
  trackPoints,
  trackOverlayMode,
  foilingChannel,
  speedChannel,
  speedRange,
  rideHeightChannel,
  rideHeightRange,
  turnRateChannel,
  turnRateRange
) {
  const coordinates = trackPoints.map((point) => [point.longitude, point.latitude]);
  if (coordinates.length < 2) {
    return buildTrackFeatureCollection(coordinates);
  }

  if (trackOverlayMode === "speed-global" || trackOverlayMode === "speed-session") {
    return buildSpeedTrackFeatureCollection(trackPoints, speedChannel, speedRange);
  }

  if (trackOverlayMode === "ride-height") {
    return buildRideHeightTrackFeatureCollection(
      trackPoints,
      rideHeightChannel,
      rideHeightRange
    );
  }

  if (trackOverlayMode === "turn-rate") {
    return buildTurnRateTrackFeatureCollection(
      trackPoints,
      turnRateChannel,
      turnRateRange
    );
  }

  if (trackOverlayMode !== "foiling") {
    return buildTrackSegmentsFeatureCollection([buildTrackFeature(coordinates)]);
  }

  const foilingLookup = prepareFoilingLookup(foilingChannel);
  if (foilingLookup.samples.length === 0) {
    return buildTrackSegmentsFeatureCollection([buildTrackFeature(coordinates)]);
  }

  const pointStates = trackPoints.map((point) => {
    const timestampMs = getTimestampMs(point?.timestamp);
    return findFoilingStateAtTime(foilingLookup, timestampMs) ?? false;
  });
  const features = [];
  let currentState = pointStates[0];
  let currentCoordinates = [coordinates[0]];

  for (let index = 1; index < coordinates.length; index += 1) {
    const segmentState = pointStates[index - 1];
    const nextCoordinate = coordinates[index];

    if (segmentState !== currentState && currentCoordinates.length > 1) {
      features.push(
        buildTrackFeature(
          currentCoordinates,
          currentState ? TRACK_FOILING_COLOR : TRACK_BASE_COLOR
        )
      );
      currentCoordinates = [coordinates[index - 1], nextCoordinate];
      currentState = segmentState;
      continue;
    }

    if (segmentState !== currentState && currentCoordinates.length === 1) {
      currentState = segmentState;
    }

    currentCoordinates.push(nextCoordinate);
  }

  if (currentCoordinates.length > 1) {
    features.push(
      buildTrackFeature(
        currentCoordinates,
        currentState ? TRACK_FOILING_COLOR : TRACK_BASE_COLOR
      )
    );
  }

  return buildTrackSegmentsFeatureCollection(features);
}

function buildPointFeature(point) {
  if (!point) {
    return {
      type: "FeatureCollection",
      features: [],
    };
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Point",
          coordinates: [point.longitude, point.latitude],
        },
      },
    ],
  };
}

function buildManeuverFeatureCollection(events, trackPoints) {
  const normalizedEvents = Array.isArray(events) ? events : [];
  const normalizedTrackPoints = Array.isArray(trackPoints) ? trackPoints : [];
  if (normalizedEvents.length === 0 || normalizedTrackPoints.length === 0) {
    return {
      type: "FeatureCollection",
      features: [],
    };
  }

  const timedTrackPoints = normalizedTrackPoints
    .map((point) => {
      const timestampMs = getTimestampMs(point?.timestamp);
      if (timestampMs === null) {
        return null;
      }

      return {
        point,
        timestampMs,
      };
    })
    .filter(Boolean);
  const timedTrackTimestamps = timedTrackPoints.map((entry) => entry.timestampMs);
  const fallbackTimestampMs = timedTrackTimestamps[0] ?? null;

  const features = normalizedEvents
    .map((event) => {
      const eventType = String(event?.event_type ?? "").toLowerCase();
      if (eventType !== "tack" && eventType !== "gybe" && eventType !== "jibe") {
        return null;
      }

      const directLatitude = toNumericValue(event?.latitude);
      const directLongitude = toNumericValue(event?.longitude);
      const normalizedEventType = eventType === "jibe" ? "gybe" : eventType;

      if (directLatitude !== null && directLongitude !== null) {
        return {
          type: "Feature",
          properties: {
            eventType: normalizedEventType,
            isFoiling: Boolean(event?.foiling),
          },
          geometry: {
            type: "Point",
            coordinates: [directLongitude, directLatitude],
          },
        };
      }

      const eventTimestampMs = getTimestampMs(event?.start_time);
      if (eventTimestampMs === null || fallbackTimestampMs === null) {
        return null;
      }

      const trackIndex = findClosestTimestampIndex(
        timedTrackTimestamps,
        eventTimestampMs
      );
      if (trackIndex < 0) {
        return null;
      }

      const trackPoint = timedTrackPoints[trackIndex]?.point;
      if (!trackPoint) {
        return null;
      }

      return {
        type: "Feature",
        properties: {
          eventType: normalizedEventType,
          isFoiling: Boolean(event?.foiling),
        },
        geometry: {
          type: "Point",
          coordinates: [trackPoint.longitude, trackPoint.latitude],
        },
      };
    })
    .filter(Boolean);

  return {
    type: "FeatureCollection",
    features,
  };
}

function getMaxSpeedTrackPoint(trackPoints, speedChannel) {
  if (!Array.isArray(trackPoints) || trackPoints.length === 0) {
    return null;
  }

  const speedLookup = prepareSpeedLookup(speedChannel);
  if (speedLookup.samples.length === 0) {
    return null;
  }

  const maxSpeedSample = speedLookup.samples.reduce((currentMax, sample) =>
    sample.value > currentMax.value ? sample : currentMax
  );
  const trackTimestamps = trackPoints.map((point) => getTimestampMs(point?.timestamp));
  const closestTrackIndex = findClosestTimestampIndex(
    trackTimestamps.map((timestamp) => timestamp ?? maxSpeedSample.timestampMs),
    maxSpeedSample.timestampMs
  );

  return closestTrackIndex >= 0 ? trackPoints[closestTrackIndex] : null;
}

function setOrCreateGeoJsonSource(map, sourceId, data, options = {}) {
  const source = map.getSource(sourceId);
  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(sourceId, { type: "geojson", data, ...options });
}

function addCircleLayerIfMissing(map, layerId, sourceId, color, radius) {
  if (map.getLayer(layerId)) {
    return;
  }

  map.addLayer({
    id: layerId,
    type: "circle",
    source: sourceId,
    paint: {
      "circle-radius": radius,
      "circle-color": color,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

function addSymbolLayerIfMissing(map, layerId, sourceId, options = {}) {
  if (map.getLayer(layerId)) {
    return;
  }

  map.addLayer({
    id: layerId,
    type: "symbol",
    source: sourceId,
    layout: {
      "text-field": options.textField ?? "★",
      "text-font": ["Open Sans Regular"],
      "text-size": options.textSize ?? 18,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
      "text-anchor": "center",
    },
    paint: {
      "text-color": options.textColor ?? "#fcffa4",
      "text-halo-color": options.textHaloColor ?? "#102033",
      "text-halo-width": options.textHaloWidth ?? 1.5,
      "text-halo-blur": options.textHaloBlur ?? 0.4,
    },
  });
}

class SmallStepZoomControl {
  constructor(step = ZOOM_BUTTON_STEP) {
    this.step = step;
    this.map = null;
    this.container = null;
    this.zoomInButton = null;
    this.zoomOutButton = null;
  }

  onAdd(map) {
    this.map = map;
    this.container = document.createElement("div");
    this.container.className = "maplibregl-ctrl maplibregl-ctrl-group";
    this.container.addEventListener("contextmenu", (event) => event.preventDefault());

    this.zoomInButton = this.createButton(
      "maplibregl-ctrl-zoom-in",
      "Zoom in",
      () => this.adjustZoom(this.step)
    );
    this.zoomOutButton = this.createButton(
      "maplibregl-ctrl-zoom-out",
      "Zoom out",
      () => this.adjustZoom(-this.step)
    );

    this.map.on("zoom", this.updateZoomButtons);
    this.updateZoomButtons();

    return this.container;
  }

  onRemove() {
    if (this.map) {
      this.map.off("zoom", this.updateZoomButtons);
    }

    this.container?.remove();
    this.map = null;
    this.container = null;
    this.zoomInButton = null;
    this.zoomOutButton = null;
  }

  createButton(className, label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", onClick);

    const icon = document.createElement("span");
    icon.className = "maplibregl-ctrl-icon";
    icon.setAttribute("aria-hidden", "true");
    button.appendChild(icon);
    this.container.appendChild(button);

    return button;
  }

  adjustZoom(delta) {
    if (!this.map) {
      return;
    }

    const nextZoom = clamp(
      this.map.getZoom() + delta,
      this.map.getMinZoom(),
      this.map.getMaxZoom()
    );

    this.map.easeTo({ zoom: nextZoom, duration: 180 });
  }

  updateZoomButtons = () => {
    if (!this.map || !this.zoomInButton || !this.zoomOutButton) {
      return;
    }

    const zoom = this.map.getZoom();
    const isMax = zoom >= this.map.getMaxZoom();
    const isMin = zoom <= this.map.getMinZoom();

    this.zoomInButton.disabled = isMax;
    this.zoomOutButton.disabled = isMin;
    this.zoomInButton.setAttribute("aria-disabled", String(isMax));
    this.zoomOutButton.setAttribute("aria-disabled", String(isMin));
  };
}

export function MapLibreTrackMapCanvas({
  replay,
  activeIndex = 0,
  trailRange = null,
  highlightRange = null,
  trackOverlayMode = "clean",
  showManeuvers = false,
  showWindPicker = false,
  windDirectionDeg = null,
  editableWindDirectionDeg = null,
  foilingChannel = null,
  maneuverEvents = null,
  maneuverTrackPoints = null,
  speedChannel = null,
  speedRange = null,
  rideHeightChannel = null,
  rideHeightRange = null,
  turnRateChannel = null,
  turnRateRange = null,
  showBoundaryMarkers = true,
  bearing = 0,
  className = "session-map-tab__canvas",
  ariaLabel = "Session track map",
  showActiveMarker = true,
  onWindDirectionChange = null,
  onWindDirectionCommit = null,
}) {
  const [mapBearingDeg, setMapBearingDeg] = useState(bearing);
  const mapElementRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const zoomControlRef = useRef(null);
  const compassControlRef = useRef(null);
  const hasFittedBoundsRef = useRef(false);
  const windOverlayRef = useRef(null);
  const isDraggingWindRef = useRef(false);
  const hasTrack = replay.trackPoints.length > 0;
  const trackIdentity = useMemo(() => {
    const firstPoint = replay.trackPoints[0] ?? null;
    const lastPoint = replay.trackPoints[replay.trackPoints.length - 1] ?? null;

    return [
      replay.trackPoints.length,
      firstPoint?.timestamp ?? "",
      firstPoint?.latitude ?? "",
      firstPoint?.longitude ?? "",
      lastPoint?.timestamp ?? "",
      lastPoint?.latitude ?? "",
      lastPoint?.longitude ?? "",
    ].join("|");
  }, [replay.trackPoints]);
  const boundedActiveIndex = Math.min(
    activeIndex,
    Math.max(replay.trackPoints.length - 1, 0)
  );
  const trackCoordinates = useMemo(
    () =>
      replay.trackPoints.map((point) => [
        point.longitude,
        point.latitude,
      ]),
    [replay.trackPoints]
  );
  const visibleTrackPoints = useMemo(() => {
    if (highlightRange) {
      return replay.trackPoints.slice(
        highlightRange.startIndex,
        highlightRange.endIndex + 1
      );
    }

    if (!trailRange) {
      return replay.trackPoints;
    }

    return replay.trackPoints.slice(trailRange.startIndex, trailRange.endIndex);
  }, [highlightRange, replay.trackPoints, trailRange]);
  const visibleTrackFeatureCollection = useMemo(
    () =>
      buildOverlayTrackFeatureCollection(
        visibleTrackPoints,
        trackOverlayMode,
        foilingChannel,
        speedChannel,
        speedRange,
        rideHeightChannel,
        rideHeightRange,
        turnRateChannel,
        turnRateRange
      ),
    [
      visibleTrackPoints,
      trackOverlayMode,
      foilingChannel,
      speedChannel,
      speedRange,
      rideHeightChannel,
      rideHeightRange,
      turnRateChannel,
      turnRateRange,
    ]
  );
  const maxSpeedTrackPoint = useMemo(() => {
    if (trackOverlayMode !== "speed-global" && trackOverlayMode !== "speed-session") {
      return null;
    }

    const candidatePoint = getMaxSpeedTrackPoint(replay.trackPoints, speedChannel);
    if (!candidatePoint) {
      return null;
    }

    return visibleTrackPoints.includes(candidatePoint) ? candidatePoint : null;
  }, [trackOverlayMode, replay.trackPoints, speedChannel, visibleTrackPoints]);
  const maneuverFeatureCollection = useMemo(
    () =>
      buildManeuverFeatureCollection(
        maneuverEvents,
        Array.isArray(replay.trackPoints)
          && replay.trackPoints.length > 0
          && replay.trackPoints.every((point) => getTimestampMs(point?.timestamp) !== null)
          ? replay.trackPoints
          : Array.isArray(maneuverTrackPoints) && maneuverTrackPoints.length > 0
            ? maneuverTrackPoints
            : replay.trackPoints
      ),
    [maneuverEvents, maneuverTrackPoints, replay.trackPoints]
  );
  const startMarkerPoint = highlightRange
    ? replay.trackPoints[highlightRange.startIndex]
    : replay.trackPoints[0];
  const endMarkerPoint = highlightRange
    ? replay.trackPoints[highlightRange.endIndex]
    : replay.trackPoints[replay.trackPoints.length - 1];
  const normalizedWindDirectionDeg = Number.isFinite(windDirectionDeg)
    ? normalizeDegrees(windDirectionDeg)
    : null;
  const normalizedEditableWindDirectionDeg = Number.isFinite(editableWindDirectionDeg)
    ? normalizeDegrees(editableWindDirectionDeg)
    : null;
  const normalizedMapBearingDeg = normalizeDegrees(mapBearingDeg);
  const windOverlayRotationDeg =
    normalizedWindDirectionDeg === null
      ? null
      : normalizedWindDirectionDeg - 90 - normalizedMapBearingDeg;
  const editableWindOverlayRotationDeg =
    normalizedEditableWindDirectionDeg === null
      ? null
      : normalizedEditableWindDirectionDeg - 90 - normalizedMapBearingDeg;

  useEffect(() => {
    if (!showWindPicker || typeof onWindDirectionCommit !== "function") {
      return undefined;
    }

    function calculateWindDirectionFromPointer(event) {
      const overlayElement = windOverlayRef.current;
      if (!overlayElement) {
        return null;
      }

      const bounds = overlayElement.getBoundingClientRect();
      const centerX = bounds.left + bounds.width / 2;
      const centerY = bounds.top + bounds.height / 2;
      const deltaX = event.clientX - centerX;
      const deltaY = event.clientY - centerY;
      if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
        return null;
      }

      return normalizeDegrees((Math.atan2(deltaY, deltaX) * 180) / Math.PI + 90);
    }

    function handlePointerMove(event) {
      if (!isDraggingWindRef.current || typeof onWindDirectionChange !== "function") {
        return;
      }

      const nextDirectionDeg = calculateWindDirectionFromPointer(event);
      if (nextDirectionDeg !== null) {
        onWindDirectionChange(
          normalizeDegrees(nextDirectionDeg + normalizedMapBearingDeg)
        );
      }
    }

    function handlePointerUp(event) {
      if (!isDraggingWindRef.current) {
        return;
      }

      isDraggingWindRef.current = false;
      const nextDirectionDeg = calculateWindDirectionFromPointer(event);
      if (nextDirectionDeg !== null) {
        onWindDirectionCommit(
          normalizeDegrees(nextDirectionDeg + normalizedMapBearingDeg)
        );
      }
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [
    normalizedMapBearingDeg,
    onWindDirectionChange,
    onWindDirectionCommit,
    showWindPicker,
  ]);

  useEffect(() => {
    hasFittedBoundsRef.current = false;
  }, [trackIdentity]);

  useEffect(() => {
    if (!mapElementRef.current || mapInstanceRef.current) {
      return undefined;
    }

    const map = new maplibregl.Map({
      container: mapElementRef.current,
      style: buildMapStyle(getMapTileUrl(), getTileAttribution()),
      center: [0, 20],
      zoom: 2,
      keyboard: false,
      bearing,
      pitch: 0,
      maxPitch: 0,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: true,
    });

    const zoomControl = new SmallStepZoomControl();
    const compassControl = new maplibregl.NavigationControl({
      showZoom: false,
      showCompass: true,
    });
    map.addControl(zoomControl, "top-left");
    map.addControl(compassControl, "top-left");
    zoomControlRef.current = zoomControl;
    compassControlRef.current = compassControl;
    mapInstanceRef.current = map;

    function handleRotate() {
      setMapBearingDeg(map.getBearing());
    }

    map.on("rotate", handleRotate);
    handleRotate();

    return () => {
      map.off("rotate", handleRotate);
      zoomControlRef.current = null;
      compassControlRef.current = null;
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) {
      return;
    }

    map.setBearing(bearing);
    setMapBearingDeg(bearing);
    map.setPitch(0);
  }, [bearing]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) {
      return undefined;
    }

    function setTrackData() {
      setOrCreateGeoJsonSource(
        map,
        "session-track-full",
        buildTrackFeatureCollection(trackCoordinates),
        {
          buffer: 256,
          tolerance: 0,
        }
      );
      setOrCreateGeoJsonSource(
        map,
        "session-track-selected",
        visibleTrackFeatureCollection,
        {
          buffer: 256,
          tolerance: 0,
        }
      );

      if (!map.getLayer("session-track-full")) {
        map.addLayer({
          id: "session-track-full",
          type: "line",
          source: "session-track-full",
          layout: {
            "line-cap": "round",
            "line-join": "round",
          },
          paint: {
            "line-color": TRACK_BASE_COLOR,
            "line-width": 4,
            "line-opacity": highlightRange ? 0.14 : 0,
          },
        });
      }

      if (!map.getLayer("session-track-selected")) {
        map.addLayer({
          id: "session-track-selected",
          type: "line",
          source: "session-track-selected",
          layout: {
            "line-cap": "round",
            "line-join": "round",
          },
          paint: {
            "line-color": ["coalesce", ["get", "color"], TRACK_BASE_COLOR],
            "line-width": 4,
            "line-opacity": 0.95,
          },
        });
      }

      map.setPaintProperty("session-track-full", "line-color", TRACK_BASE_COLOR);
      map.setPaintProperty(
        "session-track-full",
        "line-opacity",
        highlightRange ? 0.14 : 0
      );
      map.setPaintProperty(
        "session-track-selected",
        "line-color",
        ["coalesce", ["get", "color"], TRACK_BASE_COLOR]
      );
      map.setPaintProperty("session-track-selected", "line-opacity", 0.95);

      setOrCreateGeoJsonSource(
        map,
        "session-start",
        showBoundaryMarkers ? buildPointFeature(startMarkerPoint) : buildPointFeature(null)
      );
      setOrCreateGeoJsonSource(
        map,
        "session-end",
        showBoundaryMarkers ? buildPointFeature(endMarkerPoint) : buildPointFeature(null)
      );
      setOrCreateGeoJsonSource(
        map,
        "session-active",
        showActiveMarker
          ? buildPointFeature(replay.trackPoints[boundedActiveIndex])
          : buildPointFeature(null)
      );
      setOrCreateGeoJsonSource(
        map,
        "session-max-speed",
        buildPointFeature(maxSpeedTrackPoint)
      );
      setOrCreateGeoJsonSource(
        map,
        "session-maneuvers",
        maneuverFeatureCollection
      );
      addCircleLayerIfMissing(map, "session-start", "session-start", "#2fb344", 6);
      addCircleLayerIfMissing(map, "session-end", "session-end", "#d92d20", 7);
      addCircleLayerIfMissing(map, "session-active", "session-active", "#f6c671", 8);
      addSymbolLayerIfMissing(map, "session-max-speed", "session-max-speed", {
        textField: "★",
        textSize: 18,
        textColor: "#fcffa4",
        textHaloColor: "#102033",
        textHaloWidth: 1.8,
        textHaloBlur: 0.5,
      });
      if (!map.getLayer("session-maneuvers")) {
        map.addLayer({
          id: "session-maneuvers",
          type: "circle",
          source: "session-maneuvers",
          paint: {
            "circle-radius": [
              "case",
              ["boolean", ["get", "isFoiling"], false],
              11,
              8,
            ],
            "circle-color": [
              "match",
              ["get", "eventType"],
              "tack",
              MANEUVER_TACK_COLOR,
              "gybe",
              MANEUVER_GYBE_COLOR,
              TRACK_BASE_COLOR,
            ],
            "circle-stroke-color": [
              "case",
              ["boolean", ["get", "isFoiling"], false],
              MANEUVER_FOILING_RING_COLOR,
              "#ffffff",
            ],
            "circle-stroke-width": [
              "case",
              ["boolean", ["get", "isFoiling"], false],
              3.5,
              2.5,
            ],
            "circle-opacity": 0.98,
          },
        });
      }
      map.setLayoutProperty(
        "session-maneuvers",
        "visibility",
        showManeuvers ? "visible" : "none"
      );
      if (hasTrack && !hasFittedBoundsRef.current) {
        const bounds = trackCoordinates.reduce(
          (currentBounds, coordinate) => currentBounds.extend(coordinate),
          new maplibregl.LngLatBounds(trackCoordinates[0], trackCoordinates[0])
        );

        map.fitBounds(bounds, {
          padding: 40,
          maxZoom: 15,
          pitch: 0,
          bearing: map.getBearing(),
          duration: 0,
        });
        hasFittedBoundsRef.current = true;
      }
    }

    if (map.loaded()) {
      setTrackData();
      return undefined;
    }

    map.once("load", setTrackData);

    return () => {
      map.off("load", setTrackData);
    };
  }, [
    endMarkerPoint,
    hasTrack,
    highlightRange,
    maxSpeedTrackPoint,
    maneuverFeatureCollection,
    maneuverEvents,
    foilingChannel,
    trackOverlayMode,
    replay.trackPoints,
    speedChannel,
    speedRange,
    showManeuvers,
    turnRateChannel,
    turnRateRange,
    showBoundaryMarkers,
    showActiveMarker,
    startMarkerPoint,
    trackCoordinates,
    visibleTrackFeatureCollection,
  ]);

  useEffect(() => {
    const map = mapInstanceRef.current;
    const source = map?.getSource("session-active");
    if (!source) {
      return;
    }

    source.setData(
      showActiveMarker
        ? buildPointFeature(replay.trackPoints[boundedActiveIndex])
        : buildPointFeature(null)
    );
  }, [boundedActiveIndex, replay.trackPoints, showActiveMarker]);

  return (
    <div className="track-map__canvas-frame">
      <div ref={mapElementRef} className={className} aria-label={ariaLabel} />
      {showWindPicker
        && (normalizedEditableWindDirectionDeg !== null || normalizedWindDirectionDeg !== null) && (
        <div
          ref={windOverlayRef}
          className={`track-map__wind-overlay${
            typeof onWindDirectionCommit === "function"
              ? " track-map__wind-overlay--interactive"
              : ""
          }`}
          aria-hidden="true"
          onPointerDown={(event) => {
            if (typeof onWindDirectionCommit !== "function") {
              return;
            }

            event.preventDefault();
            isDraggingWindRef.current = true;
          }}
        >
          <div
            className={`track-map__wind-line${
              typeof onWindDirectionCommit === "function"
                ? " track-map__wind-line--interactive"
                : ""
            }`}
            style={{
              transform: `translate(-50%, -50%) rotate(${
                editableWindOverlayRotationDeg ?? windOverlayRotationDeg
              }deg)`,
            }}
          >
            <span className="track-map__wind-arrow" />
          </div>
          <div className="track-map__wind-center" />
        </div>
      )}
    </div>
  );
}

export function TrackReplayCard({ replay, sessionTitle, showControls = true }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const hasTrack = replay.trackPoints.length > 0;
  const hasReplay = replay.trackPoints.length > 1;
  const activePoint = hasTrack
    ? replay.trackPoints[Math.min(activeIndex, replay.trackPoints.length - 1)]
    : null;

  useEffect(() => {
    setActiveIndex((currentIndex) =>
      Math.min(currentIndex, Math.max(replay.trackPoints.length - 1, 0))
    );
    setIsPlaying(false);
  }, [replay.trackPoints.length]);

  useEffect(() => {
    if (!isPlaying || replay.trackPoints.length < 2) {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setActiveIndex((currentIndex) => {
        if (currentIndex >= replay.trackPoints.length - 1) {
          window.clearInterval(timer);
          setIsPlaying(false);
          return currentIndex;
        }

        return currentIndex + 1;
      });
    }, 420);

    return () => window.clearInterval(timer);
  }, [isPlaying, replay.trackPoints.length]);

  const activeCoordinateLabel = activePoint
    ? `${formatCoordinate(activePoint.latitude, "N", "S")} ${formatCoordinate(activePoint.longitude, "E", "W")}`
    : "Track data unavailable";

  return (
    <section className="dashboard-panel track-panel">
      <div className="section-heading">
        <div>
          <h2>Session map</h2>
        </div>
        <p className="body-copy">
          Replay the line sailed during {sessionTitle} and jump to any point in
          the session timeline.
        </p>
      </div>

      <div className="track-map">
        <div className="track-map__chrome">
          <span className="material-icons" aria-hidden="true">explore</span>
          <span>GPS route</span>
        </div>
        {showControls && hasTrack && (
          <div className="track-map__summary">
            <span>{replay.trackPoints.length} samples</span>
            <span>{activeCoordinateLabel}</span>
          </div>
        )}
        <MapLibreTrackMapCanvas
          replay={replay}
          activeIndex={activeIndex}
          className="track-map__canvas"
          ariaLabel="Session track map"
          showActiveMarker={showControls}
        />
        {!hasTrack && (
          <div className="track-map__empty">
            <span className="material-icons" aria-hidden="true">route</span>
            <p>No latitude/longitude track is available for this session yet.</p>
          </div>
        )}
        {hasTrack && (
          <div className="track-map__legend" aria-hidden="true">
            <span><span className="track-map__legend-dot track-map__legend-dot--start" />Start</span>
            <span><span className="track-map__legend-dot track-map__legend-dot--end" />Finish</span>
          </div>
        )}
      </div>

      {showControls && (
        <div className="track-controls">
          <button
            type="button"
            className="track-controls__button"
            disabled={!hasReplay}
            onClick={() => {
              if (!hasReplay) {
                return;
              }

              if (activeIndex === replay.trackPoints.length - 1) {
                setActiveIndex(0);
              }

              setIsPlaying((currentValue) => !currentValue);
            }}
          >
            <span className="material-icons" aria-hidden="true">
              {isPlaying ? "pause" : "play_arrow"}
            </span>
            <span>{isPlaying ? "Pause" : "Play"}</span>
          </button>

          <div className="track-controls__timeline">
            <input
              type="range"
              min="0"
              max={Math.max(replay.trackPoints.length - 1, 0)}
              value={Math.min(activeIndex, Math.max(replay.trackPoints.length - 1, 0))}
              disabled={!hasReplay}
              onChange={(event) => {
                setIsPlaying(false);
                setActiveIndex(Number(event.target.value));
              }}
            />
            <div className="track-controls__labels">
              <span>{activePoint?.elapsedLabel ?? "No track"}</span>
              <span>{replay.durationLabel}</span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
