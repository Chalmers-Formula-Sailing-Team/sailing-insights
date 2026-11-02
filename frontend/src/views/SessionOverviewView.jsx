import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { projectTrackPoints } from "../utils/trackMap.js";
import { MapDataField } from "./components/MapDataField.jsx";
import { MetricCard } from "./components/MetricCard.jsx";
import { RaceCard } from "./components/RaceCard.jsx";
import { RaceFormModal } from "./components/RaceFormModal.jsx";
import { RaceWizardModal } from "./components/RaceWizardModal.jsx";
import { RingChart } from "./components/RingChart.jsx";
import { TimeSeriesChart } from "./components/TimeSeriesChart.jsx";
import {
  MapLibreTrackMapCanvas,
  TrackReplayCard,
} from "./components/TrackReplayCard.jsx";

const PLAYBACK_SPEEDS = [1, 2, 4, 10];
const NOTES_AUTOSAVE_DELAY_MS = 700;
const DEFAULT_VIDEO_FILE_PATH = "~/Downloads";
const DEFAULT_VIDEO_OUTPUT_FOLDER = "~/Downloads";
const TRACK_TRAIL_OPTIONS = [
  { value: "full", label: "Full" },
  { value: "past", label: "Past" },
  { value: "past-forgetting", label: "Past with forgetting" },
  { value: "none", label: "None" },
];
const MAP_TRACK_OVERLAY_OPTIONS = [
  { value: "clean", label: "Clean" },
  { value: "foiling", label: "Foiling" },
  { value: "ride-height", label: "Ride height" },
  { value: "turn-rate", label: "Turn rate" },
  { value: "speed-global", label: "Speed (global range)" },
  { value: "speed-session", label: "Speed (session)" },
];
const MAP_MARKER_OVERLAY_OPTIONS = [{ value: "maneuvers", label: "Maneuvers" }];

const RACE_FOILING_SPEED_KTS = 7;
const TURN_RATE_OVERLAY_MAX_ABS = 20;
const VIDEO_PROGRESS_POLL_INTERVAL_MS = 600;
const VIDEO_OVERLAY_POSITION_OPTIONS = ["top", "bottom", "left", "right"];
const VIDEO_OVERLAY_FIELDS_PER_POSITION = 3;
const UTC_VIDEO_CHANNEL_OPTION = {
  id: "virtual-time-utc",
  name: "time_utc",
  unit: "",
  source: "virtual",
  values: [true],
};

function delay(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

function formatDurationFromHours(durationHours) {
  const totalSeconds = Math.round(Math.max(durationHours, 0) * 3600);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }

  return `${seconds}s`;
}

function formatChannelOverlayLabel(channel) {
  const unitSuffix = channel.unit ? ` (${channel.unit})` : "";
  return `${String(channel.name || "").toUpperCase()}${unitSuffix}`;
}

function createEmptyVideoOverlayLayout() {
  return Object.fromEntries(
    VIDEO_OVERLAY_POSITION_OPTIONS.map((position) => [
      position,
      Array.from({ length: VIDEO_OVERLAY_FIELDS_PER_POSITION }, () => ""),
    ])
  );
}

function flattenVideoOverlayLayout(layout) {
  return VIDEO_OVERLAY_POSITION_OPTIONS.flatMap((position) =>
    Array.isArray(layout?.[position]) ? layout[position].filter(Boolean) : []
  );
}

function buildDefaultVideoOverlayLayout(availableChannelNames) {
  const nextLayout = createEmptyVideoOverlayLayout();
  const preferredChannelNames = availableChannelNames.includes("sog")
    ? ["sog", ...availableChannelNames.filter((channelName) => channelName !== "sog")]
    : availableChannelNames;
  const defaultChannelNames = preferredChannelNames.slice(
    0,
    VIDEO_OVERLAY_FIELDS_PER_POSITION
  );
  nextLayout.bottom = nextLayout.bottom.map((_, index) => defaultChannelNames[index] ?? "");
  return nextLayout;
}

function formatNumber(value, unit, fractionDigits = 1) {
  if (!Number.isFinite(value)) {
    return `0${unit ? ` ${unit}` : ""}`;
  }

  return `${value.toFixed(fractionDigits)}${unit ? ` ${unit}` : ""}`;
}

function formatSpeedLegendLabel(value) {
  return formatNumber(Math.max(0, value), "kn");
}

function formatTurnRateLegendLabel(value) {
  if (!Number.isFinite(value)) {
    return "0 deg/s";
  }

  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)} deg/s`;
}

function formatRideHeightLegendLabel(value) {
  return formatNumber(Math.max(0, value), "m", 2);
}

function formatDegreesLabel(value) {
  if (!Number.isFinite(value)) {
    return "No data";
  }

  const normalizedValue = ((Math.round(value) % 360) + 360) % 360;
  return `${normalizedValue}°`;
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360;
}

function isEditableElement(element) {
  if (!(element instanceof HTMLElement)) {
    return false;
  }

  return (
    element.isContentEditable ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName)
  );
}

function toNumericValue(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : null;
}

function getChannelByName(channels, names) {
  return channels.find((channel) => names.includes(channel.name));
}

function buildTrackPointsFromChannels(channels) {
  const latChannel = getChannelByName(channels, ["lat"]);
  const lonChannel = getChannelByName(channels, ["lon"]);
  const latValues = latChannel?.values ?? [];
  const lonValues = lonChannel?.values ?? [];
  const lonValuesByTimestamp = new Map(
    lonValues.map((value) => [value.timestamp, value.value])
  );

  return latValues
    .map((latValue, index) => {
      const latitude = toNumericValue(latValue.value);
      const longitude = toNumericValue(
        lonValuesByTimestamp.has(latValue.timestamp)
          ? lonValuesByTimestamp.get(latValue.timestamp)
          : lonValues[index]?.value
      );

      if (latitude === null || longitude === null) {
        return null;
      }

      return {
        latitude,
        longitude,
        timestamp: latValue.timestamp,
      };
    })
    .filter(Boolean);
}

function toRadians(value) {
  return (value * Math.PI) / 180;
}

function calculateDistanceNm(trackPoints) {
  if (trackPoints.length < 2) {
    return 0;
  }

  const earthRadiusM = 6371000;
  let distanceM = 0;

  for (let index = 1; index < trackPoints.length; index += 1) {
    const previousPoint = trackPoints[index - 1];
    const point = trackPoints[index];
    const latA = toRadians(previousPoint.latitude);
    const latB = toRadians(point.latitude);
    const deltaLat = toRadians(point.latitude - previousPoint.latitude);
    const deltaLon = toRadians(point.longitude - previousPoint.longitude);
    const halfChord =
      Math.sin(deltaLat / 2) ** 2 +
      Math.cos(latA) * Math.cos(latB) * Math.sin(deltaLon / 2) ** 2;
    const angularDistance =
      2 * Math.atan2(Math.sqrt(halfChord), Math.sqrt(1 - halfChord));
    distanceM += earthRadiusM * angularDistance;
  }

  return distanceM / 1852;
}

function calculateFoilingStats(channels, durationMinutes) {
  const foilingChannel = getChannelByName(channels, ["foiling"]);
  const speedChannel = getChannelByName(channels, ["sog", "inferred_SOG"]);
  const hasFoilingSource =
    (foilingChannel?.values?.length ?? 0) > 1 ||
    (speedChannel?.values?.length ?? 0) > 1;
  const sourceValues = foilingChannel?.values?.length
    ? foilingChannel.values.map((value) => ({
        timestamp: value.timestamp,
        isFoiling: Boolean(value.value),
      }))
    : (speedChannel?.values ?? []).map((value) => ({
        timestamp: value.timestamp,
        isFoiling: Number(value.value) >= RACE_FOILING_SPEED_KTS,
      }));

  if (sourceValues.length < 2) {
    return { foilingTimeMin: 0, foilingPercent: 0, hasFoilingSource };
  }

  let foilingMs = 0;
  let totalMs = 0;

  for (let index = 1; index < sourceValues.length; index += 1) {
    const previousTimestamp = getTimestampMs(sourceValues[index - 1].timestamp);
    const timestamp = getTimestampMs(sourceValues[index].timestamp);
    if (previousTimestamp === null || timestamp === null || timestamp <= previousTimestamp) {
      continue;
    }

    const deltaMs = timestamp - previousTimestamp;
    totalMs += deltaMs;
    if (sourceValues[index - 1].isFoiling) {
      foilingMs += deltaMs;
    }
  }

  const fallbackTotalMs = durationMinutes * 60 * 1000;
  const denominatorMs = totalMs || fallbackTotalMs;
  const foilingTimeMin = foilingMs / 60000;

  return {
    foilingTimeMin,
    foilingPercent: denominatorMs > 0 ? (foilingMs / denominatorMs) * 100 : 0,
    hasFoilingSource,
  };
}

function countRaceEvents(events, names) {
  return events.filter((event) =>
    names.includes(String(event.event_type ?? "").toLowerCase())
  ).length;
}

function countFoilingRaceEvents(events, names) {
  return events.filter((event) => {
    const eventType = String(event.event_type ?? "").toLowerCase();
    return names.includes(eventType) && Boolean(event.foiling);
  }).length;
}

function clampPercentage(value) {
  return Math.min(Math.max(Number(value) || 0, 0), 100);
}

function calculatePercentage(part, total) {
  if (!Number.isFinite(part) || !Number.isFinite(total) || total <= 0) {
    return 0;
  }

  return (part / total) * 100;
}

function buildRaceManeuverFoilingChart({
  title,
  totalCount,
  foilingCount,
  activeColor,
  inactiveColor,
}) {
  const safeTotalCount = Math.max(0, Math.round(Number(totalCount) || 0));
  const safeFoilingCount = Math.min(
    safeTotalCount,
    Math.max(0, Math.round(Number(foilingCount) || 0))
  );
  const foilingPercentage = clampPercentage(
    calculatePercentage(safeFoilingCount, safeTotalCount)
  );

  return {
    title,
    centerValue: `${foilingPercentage.toFixed(1)}%`,
    subtitle:
      safeTotalCount > 0
        ? `${safeFoilingCount} of ${safeTotalCount} foiling`
        : "No maneuvers recorded",
    segments: [
      {
        label: "Foiling",
        value: foilingPercentage,
        color: activeColor,
      },
      {
        label: "Non-foiling",
        value: Math.max(0, 100 - foilingPercentage),
        color: inactiveColor,
      },
    ],
  };
}

function deriveRaceStats(raceData, selectedRace, baseSession = null) {
  const channels = raceData?.channels ?? [];
  const events = raceData?.events ?? [];
  const trackPoints = buildTrackPointsFromChannels(channels);
  const startTimeMs = getTimestampMs(selectedRace?.startTime);
  const endTimeMs = getTimestampMs(selectedRace?.endTime);
  const fallbackDurationHours = baseSession?.durationHours ?? 0;
  const durationHours =
    startTimeMs !== null && endTimeMs !== null && endTimeMs > startTimeMs
      ? (endTimeMs - startTimeMs) / 3600000
      : fallbackDurationHours;
  const durationMinutes = durationHours * 60;
  const speedChannel = getChannelByName(channels, ["sog", "inferred_SOG"]);
  const speedValues = (speedChannel?.values ?? [])
    .map((value) => Number(value.value))
    .filter(Number.isFinite);
  const distanceNm = calculateDistanceNm(trackPoints);
  const foilingStats = calculateFoilingStats(channels, durationMinutes);
  const tacks = countRaceEvents(events, ["tack"]);
  const gybes = countRaceEvents(events, ["gybe", "jibe"]);
  const foilingTacks = countFoilingRaceEvents(events, ["tack"]);
  const foilingGybes = countFoilingRaceEvents(events, ["gybe", "jibe"]);
  const capsizes = countRaceEvents(events, ["capsize"]);

  return {
    channels,
    events,
    trackPoints,
    durationHours,
    durationMinutes,
    distanceNm,
    hasDistance: trackPoints.length > 1,
    maxSpeedKts: speedValues.length ? Math.max(...speedValues) : 0,
    hasSpeed: speedValues.length > 0,
    foilingTimeMin: foilingStats.foilingTimeMin,
    foilingPercent: foilingStats.foilingPercent,
    hasFoiling: foilingStats.hasFoilingSource,
    tacks,
    gybes,
    foilingTacks,
    foilingGybes,
    foilingTackPercentage: calculatePercentage(foilingTacks, tacks),
    foilingGybePercentage: calculatePercentage(foilingGybes, gybes),
    capsizes,
    hasEvents: Boolean(raceData),
  };
}

function buildRaceScopedSession(baseSession, raceData, selectedRace) {
  if (!raceData || !selectedRace) {
    return baseSession;
  }

  const raceStats = deriveRaceStats(raceData, selectedRace, baseSession);
  const projectedTrackPoints = projectTrackPoints(raceStats.trackPoints);
  const durationLabel = formatDurationFromHours(raceStats.durationHours);

  return {
    ...baseSession,
    title: `${selectedRace.name} - ${baseSession.title}`,
    data: raceData,
    durationHours: raceStats.durationHours,
    distanceNm: raceStats.distanceNm,
    maxSpeedKts: raceStats.maxSpeedKts,
    foilingPercent: raceStats.foilingPercent,
    foilingTimeMin: raceStats.foilingTimeMin,
    tacks: raceStats.tacks,
    gybes: raceStats.gybes,
    foilingTacks: raceStats.foilingTacks,
    foilingGybes: raceStats.foilingGybes,
    foilingTackPercentage: raceStats.foilingTackPercentage,
    foilingGybePercentage: raceStats.foilingGybePercentage,
    capsizes: raceStats.capsizes,
    summary: {
      duration: durationLabel,
      distance: raceStats.hasDistance ? formatNumber(raceStats.distanceNm, "nm") : "--",
      maxSpeed: raceStats.hasSpeed ? formatNumber(raceStats.maxSpeedKts, "kn") : "--",
      foilingTime: raceStats.hasFoiling
        ? formatDurationFromHours(raceStats.foilingTimeMin / 60)
        : "--",
      foilingAverage: raceStats.hasFoiling
        ? `${raceStats.foilingPercent.toFixed(1)}%`
        : "--",
      tacks: `${raceStats.tacks}`,
      gybes: `${raceStats.gybes}`,
      capsizes: `${raceStats.capsizes}`,
    },
    foilingChart: {
      ...baseSession.foilingChart,
      centerValue: raceStats.hasFoiling
        ? `${raceStats.foilingPercent.toFixed(1)}%`
        : "--",
      subtitle: raceStats.hasFoiling
        ? `${formatDurationFromHours(raceStats.foilingTimeMin / 60)} total fly time`
        : "No race foiling data",
      segments: [
        {
          label: "Foiling",
          value: raceStats.hasFoiling
            ? Math.min(Math.max(raceStats.foilingPercent, 0), 100)
            : 0,
          color: "#0f766e",
        },
        {
          label: "Displacement",
          value: raceStats.hasFoiling
            ? Math.max(0, 100 - Math.min(Math.max(raceStats.foilingPercent, 0), 100))
            : 100,
          color: "#d7e7e2",
        },
      ],
    },
    foilingTackChart: buildRaceManeuverFoilingChart({
      title: "Foiling tacks",
      totalCount: raceStats.tacks,
      foilingCount: raceStats.foilingTacks,
      activeColor: "#0f766e",
      inactiveColor: "#d7e7e2",
    }),
    foilingGybeChart: buildRaceManeuverFoilingChart({
      title: "Foiling gybes",
      totalCount: raceStats.gybes,
      foilingCount: raceStats.foilingGybes,
      activeColor: "#c56a1b",
      inactiveColor: "#f3dfc7",
    }),
    replay: {
      durationLabel,
      trackPoints: projectedTrackPoints.map((point, index, points) => {
        const elapsedMinutes = Math.round(
          (index / Math.max(points.length - 1, 1)) * raceStats.durationMinutes
        );

        return {
          ...point,
          elapsedMinutes,
          elapsedLabel: formatDurationFromHours(elapsedMinutes / 60),
        };
      }),
    },
  };
}

function formatElapsedTimeFromRange(startTime, endTime) {
  const startTimeMs = new Date(startTime).getTime();
  const endTimeMs = new Date(endTime).getTime();
  if (
    Number.isNaN(startTimeMs) ||
    Number.isNaN(endTimeMs) ||
    endTimeMs <= startTimeMs
  ) {
    return "TBD";
  }

  return formatDurationFromHours((endTimeMs - startTimeMs) / 3600000);
}

function mapPersistedRaceToCard(race, raceData = null) {
  const raceStats = raceData ? deriveRaceStats(raceData, race) : null;
  const maneuvers =
    raceStats && raceStats.hasEvents ? raceStats.tacks + raceStats.gybes : null;

  return {
    id: race.id,
    name: race.name,
    startTime: race.startTime,
    endTime: race.endTime,
    elapsedTime: formatElapsedTimeFromRange(race.startTime, race.endTime),
    distance: raceStats?.hasDistance ? formatNumber(raceStats.distanceNm, "nm") : "--",
    foilingPercentage: raceStats?.hasFoiling
      ? `${raceStats.foilingPercent.toFixed(1)}%`
      : "--",
    maneuvers: maneuvers === null ? "--" : maneuvers,
  };
}

function formatPlaybackTime(totalSeconds) {
  const safeTotalSeconds = Math.max(Math.round(totalSeconds), 0);
  const hours = Math.floor(safeTotalSeconds / 3600);
  const minutes = Math.floor((safeTotalSeconds % 3600) / 60);
  const seconds = safeTotalSeconds % 60;
  const paddedSeconds = String(seconds).padStart(2, "0");

  if (hours === 0) {
    return `${minutes}:${paddedSeconds}`;
  }

  return `${hours}:${String(minutes).padStart(2, "0")}:${paddedSeconds}`;
}

function formatUtcTime(timestampMs) {
  if (timestampMs === null) {
    return "No data";
  }

  const date = new Date(timestampMs);
  if (Number.isNaN(date.getTime())) {
    return "No data";
  }

  return date.toISOString().slice(11, 19);
}

function getTimestampMs(value) {
  if (!value) {
    return null;
  }

  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function getTrackPointTimestampMs(point) {
  return getTimestampMs(point?.timestamp);
}

function findClosestTimestampIndex(timestamps, timestampMs) {
  if (!Array.isArray(timestamps) || timestamps.length === 0) {
    return 0;
  }

  if (timestampMs === null) {
    return 0;
  }

  let low = 0;
  let high = timestamps.length - 1;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    const timestamp = timestamps[middle];

    if (timestamp < timestampMs) {
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

function findTrackIndexAtTime(trackPoints, timestampMs) {
  if (!Array.isArray(trackPoints) || trackPoints.length === 0) {
    return 0;
  }

  return findClosestTimestampIndex(
    trackPoints.map((point) => getTrackPointTimestampMs(point) ?? timestampMs ?? 0),
    timestampMs
  );
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

function findLastTimestampIndexAtOrBefore(timestamps, timestampMs) {
  let low = 0;
  let high = timestamps.length;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] <= timestampMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }

  return low - 1;
}

function findFirstTimestampIndexAtOrAfter(timestamps, timestampMs) {
  let low = 0;
  let high = timestamps.length;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] < timestampMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }

  return low;
}

function prepareTrackPointTimestamps(trackPoints) {
  const timestamps = trackPoints.map((point) => getTrackPointTimestampMs(point));
  return {
    timestamps,
    areAllValid: timestamps.every((timestamp) => timestamp !== null),
  };
}

function prepareChannelLookup(channel) {
  const values = Array.isArray(channel.values) ? channel.values : [];
  const timestamps = values.map((value) => getTimestampMs(value?.timestamp));
  const validTimestamps = timestamps.filter((timestamp) => timestamp !== null);

  return {
    ...channel,
    values,
    timestamps,
    hasOnlyValidTimestamps: validTimestamps.length === values.length,
    sampleToleranceMs: getSampleToleranceMs(validTimestamps),
  };
}

function findChannelValueAtTime(channel, activeTimestampMs, activeRatio) {
  const values = channel.values;
  if (values.length === 0) {
    return null;
  }

  if (activeTimestampMs === null) {
    const index = Math.round(activeRatio * Math.max(values.length - 1, 0));
    return values[index]?.value ?? null;
  }

  let low = 0;
  let high = values.length - 1;
  const timestamps = channel.timestamps;

  if (!channel.hasOnlyValidTimestamps) {
    return findChannelValueAtTimeFallback(channel, activeTimestampMs, activeRatio);
  }

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    const timestamp = timestamps[middle];

    if (timestamp < activeTimestampMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }

  const current = values[low];
  const previous = values[Math.max(low - 1, 0)];
  const currentDelta = Math.abs(timestamps[low] - activeTimestampMs);
  const previousDelta =
    Math.abs(timestamps[Math.max(low - 1, 0)] - activeTimestampMs);
  const nearestDelta = Math.min(currentDelta, previousDelta);

  if (nearestDelta > channel.sampleToleranceMs) {
    return null;
  }

  return previousDelta <= currentDelta ? previous?.value ?? null : current?.value ?? null;
}

function findChannelValueAtTimeFallback(channel, activeTimestampMs, activeRatio) {
  const values = channel.values;
  if (values.length === 0) {
    return null;
  }

  if (activeTimestampMs === null) {
    const index = Math.round(activeRatio * Math.max(values.length - 1, 0));
    return values[index]?.value ?? null;
  }

  let low = 0;
  let high = values.length - 1;

  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    const timestamp = getTimestampMs(values[middle]?.timestamp);

    if (timestamp !== null && timestamp < activeTimestampMs) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }

  const current = values[low];
  const previous = values[Math.max(low - 1, 0)];
  const currentDelta =
    Math.abs((getTimestampMs(current?.timestamp) ?? activeTimestampMs) - activeTimestampMs);
  const previousDelta =
    Math.abs((getTimestampMs(previous?.timestamp) ?? activeTimestampMs) - activeTimestampMs);
  const nearestDelta = Math.min(currentDelta, previousDelta);

  if (nearestDelta > channel.sampleToleranceMs) {
    return null;
  }

  return previousDelta <= currentDelta ? previous?.value ?? null : current?.value ?? null;
}

function findChannel(channels, names) {
  return channels.find((channel) => names.includes(channel.name));
}

function orderMapChannels(channels) {
  const preferredNames = ["sog", "inferred_SOG"];
  const preferredChannels = preferredNames
    .map((name) => channels.find((channel) => channel.name === name))
    .filter(Boolean);
  const remainingChannels = channels.filter(
    (channel) => !preferredNames.includes(channel.name)
  );

  return [...preferredChannels, ...remainingChannels];
}

function getTrailRange(trackPoints, trackPointTimestamps, mode, activeTimestampMs, activeIndex) {
  if (mode === "full") {
    return null;
  }

  if (mode === "none") {
    return { startIndex: 0, endIndex: 0 };
  }

  const clampedEndIndex = Math.min(activeIndex + 1, trackPoints.length);
  if (activeTimestampMs === null || !trackPointTimestamps.areAllValid) {
    return { startIndex: 0, endIndex: clampedEndIndex };
  }

  const endIndex =
    findLastTimestampIndexAtOrBefore(trackPointTimestamps.timestamps, activeTimestampMs) + 1;

  if (endIndex <= 0) {
    return { startIndex: 0, endIndex: 0 };
  }

  if (mode === "past") {
    return { startIndex: 0, endIndex };
  }

  const minTimestampMs = activeTimestampMs - 2 * 60 * 1000;
  const startIndex = findFirstTimestampIndexAtOrAfter(
    trackPointTimestamps.timestamps,
    minTimestampMs
  );

  return {
    startIndex: Math.min(startIndex, endIndex),
    endIndex,
  };
}

function buildMapOverlayLegend(type, options = {}) {
  if (type === "wind") {
    return {
      type,
      title: "Wind picker",
      directionLabel: options.directionLabel,
    };
  }

  if (type === "foiling") {
    return {
      type,
      title: "Foiling overlay",
    };
  }

  if (type === "maneuvers") {
    return {
      type,
      title: "Maneuver overlay",
    };
  }

  if (type === "turn-rate") {
    return {
      type,
      title: "Turn rate overlay",
      minLabel: formatTurnRateLegendLabel(-TURN_RATE_OVERLAY_MAX_ABS),
      centerLabel: "0 deg/s",
      maxLabel: formatTurnRateLegendLabel(TURN_RATE_OVERLAY_MAX_ABS),
    };
  }

  if (type === "ride-height") {
    return {
      type,
      title: "Ride height overlay",
      minLabel: formatRideHeightLegendLabel(options.range?.min ?? 0),
      maxLabel: formatRideHeightLegendLabel(options.range?.max ?? 0),
    };
  }

  if (type === "speed-global" || type === "speed-session") {
    return {
      type: "speed",
      title:
        type === "speed-global"
          ? "Speed range across all sessions"
          : "Speed range in this session",
      minLabel: formatSpeedLegendLabel(options.range?.min ?? 0),
      maxLabel: formatSpeedLegendLabel(options.range?.max ?? 0),
    };
  }

  return null;
}

export function SessionOverviewView({
  sessionDetail,
  onSessionManualWindDirectionChange,
  onSessionNotesChange,
  onSessionVideoTrigger,
  onVideoJobStatusLoad,
  onSessionRaceCreate,
  onSessionRaceUpdate,
  onSessionRaceDelete,
  onSessionRaceDataLoad,
  onSessionRaceSelect,
  onSessionExport,
  onSessionRacesExport,
  onRaceExport,
  onRaceScopeClear,
  onBackToBoat,
}) {
  const [activeTab, setActiveTab] = useState("overview");
  const [isRaceWizardOpen, setIsRaceWizardOpen] = useState(false);
  const [editingRace, setEditingRace] = useState(null);
  const [deletingRace, setDeletingRace] = useState(null);
  const [raceDeleteErrorMessage, setRaceDeleteErrorMessage] = useState("");
  const [isDeletingRace, setIsDeletingRace] = useState(false);
  const [loadingRaceId, setLoadingRaceId] = useState(null);
  const [mapActiveIndex, setMapActiveIndex] = useState(0);
  const [isMapPlaying, setIsMapPlaying] = useState(false);
  const [mapPlaybackSpeed, setMapPlaybackSpeed] = useState(1);
  const [mapPlaybackTimestampMs, setMapPlaybackTimestampMs] = useState(null);
  const [isMapSettingsOpen, setIsMapSettingsOpen] = useState(false);
  const [mapSettingsSection, setMapSettingsSection] = useState("overlays");
  const [trackTrailMode, setTrackTrailMode] = useState("full");
  const [mapTrackOverlayMode, setMapTrackOverlayMode] = useState("clean");
  const [mapMarkerOverlayModes, setMapMarkerOverlayModes] = useState([]);
  const [isWindPickerEnabled, setIsWindPickerEnabled] = useState(false);
  const [manualWindDirectionDraftDeg, setManualWindDirectionDraftDeg] = useState(null);
  const [manualWindDirectionSaveState, setManualWindDirectionSaveState] = useState("saved");
  const [manualWindDirectionErrorMessage, setManualWindDirectionErrorMessage] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [notesSaveState, setNotesSaveState] = useState("saved");
  const [notesErrorMessage, setNotesErrorMessage] = useState("");
  const [videoFilePath, setVideoFilePath] = useState(DEFAULT_VIDEO_FILE_PATH);
  const [videoOutputFolder, setVideoOutputFolder] = useState("");
  const [videoOverlayLayout, setVideoOverlayLayout] = useState(() =>
    createEmptyVideoOverlayLayout()
  );
  const [videoTriggerState, setVideoTriggerState] = useState("idle");
  const [videoTriggerMessage, setVideoTriggerMessage] = useState("");
  const [videoProgressPercent, setVideoProgressPercent] = useState(0);
  const [videoOutputFilePath, setVideoOutputFilePath] = useState("");
  const [videoJobId, setVideoJobId] = useState("");
  const [isExporting, setIsExporting] = useState(false);
  const mapTabRef = useRef(null);
  const videoPollRequestRef = useRef(0);
  const persistedNotesRef = useRef("");
  const latestNotesRequestRef = useRef(0);
  const latestNotesDraftRef = useRef("");
  const {
    boat,
    session: baseSession,
    selectedRaceId,
    raceData,
    raceDataByRaceId = {},
  } = sessionDetail;
  const selectedRace =
    raceData?.races?.[0] ??
    (baseSession.data?.races ?? []).find((race) => race.id === selectedRaceId) ??
    null;
  const isRaceScoped = Boolean(selectedRaceId && raceData && selectedRace);
  const session = isRaceScoped
    ? buildRaceScopedSession(baseSession, raceData, selectedRace)
    : baseSession;
  const persistedNotes = baseSession.data?.session?.notes ?? baseSession.notes ?? "";
  const persistedManualWindDirectionDeg = baseSession.manualWindDirectionDeg;
  latestNotesDraftRef.current = notesDraft;
  const mapChannels = session.data?.channels ?? [];
  const availableVideoChannels = useMemo(
    () =>
      [
        UTC_VIDEO_CHANNEL_OPTION,
        ...mapChannels.filter(
          (channel) => Array.isArray(channel.values) && channel.values.length > 0
        ),
      ].sort((left, right) =>
        formatChannelOverlayLabel(left).localeCompare(formatChannelOverlayLabel(right))
      ),
    [mapChannels]
  );
  const selectedVideoChannels = useMemo(
    () => flattenVideoOverlayLayout(videoOverlayLayout),
    [videoOverlayLayout]
  );
  const mapEvents = session.data?.events ?? [];
  const maneuverTrackPoints = useMemo(
    () => buildTrackPointsFromChannels(mapChannels),
    [mapChannels]
  );
  const mapReplayTrackPoints = maneuverTrackPoints.length > 0
    ? maneuverTrackPoints
    : session.replay.trackPoints;
  const mapReplay = useMemo(
    () => ({
      ...session.replay,
      trackPoints: mapReplayTrackPoints,
    }),
    [session.replay, mapReplayTrackPoints]
  );
  const hasMapReplay = mapReplay.trackPoints.length > 1;
  const mapTrackStartTimestampMs =
    getTrackPointTimestampMs(mapReplay.trackPoints[0]) ??
    getTimestampMs(session.data?.session?.start_at);
  const mapTrackEndTimestampMs =
    getTrackPointTimestampMs(mapReplay.trackPoints[mapReplay.trackPoints.length - 1]) ??
    (mapTrackStartTimestampMs === null
      ? null
      : mapTrackStartTimestampMs + session.durationHours * 3600 * 1000);
  const mapActivePoint =
    mapReplay.trackPoints[Math.min(mapActiveIndex, Math.max(mapReplay.trackPoints.length - 1, 0))];
  const mapActivePointTimestampMs = getTimestampMs(mapActivePoint?.timestamp);
  const sessionStartTimestampMs = getTimestampMs(session.data?.session?.start_at);
  const mapActiveTimestampMs =
    mapPlaybackTimestampMs ??
    mapActivePointTimestampMs ??
    (sessionStartTimestampMs === null
      ? mapTrackStartTimestampMs
      : sessionStartTimestampMs);
  const mapDurationSeconds =
    mapTrackStartTimestampMs !== null && mapTrackEndTimestampMs !== null
      ? (mapTrackEndTimestampMs - mapTrackStartTimestampMs) / 1000
      : session.durationHours * 3600;
  const mapDisplayedActiveSeconds =
    mapActiveTimestampMs !== null && mapTrackStartTimestampMs !== null
      ? (mapActiveTimestampMs - mapTrackStartTimestampMs) / 1000
      : 0;
  const mapActiveRatio =
    mapActiveTimestampMs !== null &&
    mapTrackStartTimestampMs !== null &&
    mapTrackEndTimestampMs !== null &&
    mapTrackEndTimestampMs > mapTrackStartTimestampMs
      ? (mapActiveTimestampMs - mapTrackStartTimestampMs) /
        (mapTrackEndTimestampMs - mapTrackStartTimestampMs)
      : Math.min(mapActiveIndex, Math.max(mapReplay.trackPoints.length - 1, 0)) /
        Math.max(mapReplay.trackPoints.length - 1, 1);
  const foilingChannel = findChannel(mapChannels, ["foiling"]);
  const rideHeightChannel = findChannel(mapChannels, ["height_m"]);
  const speedChannel = findChannel(mapChannels, ["sog", "inferred_SOG"]);
  const turnRateChannel = findChannel(mapChannels, ["turn_rate"]);
  const boatMaxSpeedKts = Math.max(0, Number(boat.maxSpeedKts ?? 0));
  const sessionMaxSpeedKts = Math.max(0, Number(session.maxSpeedKts ?? 0));
  const speedOverlayRange =
    mapTrackOverlayMode === "speed-global"
      ? { min: 0, max: boatMaxSpeedKts }
      : mapTrackOverlayMode === "speed-session"
        ? { min: 0, max: sessionMaxSpeedKts }
        : null;
  const turnRateOverlayRange = { maxAbs: TURN_RATE_OVERLAY_MAX_ABS };
  const rideHeightOverlayRange = useMemo(() => {
    const values = rideHeightChannel?.values ?? [];
    const numericValues = values
      .map((entry) => toNumericValue(entry?.value))
      .filter(Number.isFinite);

    if (numericValues.length === 0) {
      return null;
    }

    return {
      min: Math.min(...numericValues),
      max: Math.max(...numericValues),
    };
  }, [rideHeightChannel]);
  const preparedTrackPoints = useMemo(
    () => prepareTrackPointTimestamps(mapReplay.trackPoints),
    [mapReplay.trackPoints]
  );
  const preparedMapChannels = useMemo(
    () => orderMapChannels(mapChannels).map((channel) => prepareChannelLookup(channel)),
    [mapChannels]
  );
  const preparedRelativeTimeChannel = findChannel(preparedMapChannels, ["time_rel_s"]);
  const preparedRideHeightChannel = findChannel(preparedMapChannels, ["height_m"]);
  const preparedMapChannelsWithoutRelativeTime = useMemo(
    () =>
      preparedMapChannels.filter(
        (channel) => channel.name !== "time_rel_s" && channel.name !== "height_m"
      ),
    [preparedMapChannels]
  );
  const sogChannel = findChannel(mapChannels, ["sog"]);
  const inferredSogChannel = findChannel(mapChannels, ["inferred_SOG"]);
  const heartRateChannel = findChannel(mapChannels, ["heart_rate", "hr"]);
  const windSpeedChannel = findChannel(mapChannels, ["tws_external", "wind_amt"]);
  const windGustChannel = findChannel(mapChannels, ["twg_external", "wind_gust_amt"]);
  const windDirectionChannel = findChannel(mapChannels, ["twd_external", "wind_dir"]);
  const preparedWindDirectionChannel = findChannel(preparedMapChannels, [
    "twd_external",
    "wind_dir",
  ]);
  const hasWindSeries =
    (windSpeedChannel?.values?.length ?? 0) > 0 ||
    (windGustChannel?.values?.length ?? 0) > 0 ||
    (windDirectionChannel?.values?.length ?? 0) > 0;
  const mapDisplayedWindDirectionDeg = useMemo(() => {
    const channelValue = preparedWindDirectionChannel
      ? toNumericValue(
          findChannelValueAtTime(
            preparedWindDirectionChannel,
            mapActiveTimestampMs,
            mapActiveRatio
          )
        )
      : null;

    if (Number.isFinite(channelValue)) {
      return normalizeDegrees(channelValue);
    }

    if (Number.isFinite(session.manualWindDirectionDeg)) {
      return normalizeDegrees(session.manualWindDirectionDeg);
    }

    return null;
  }, [
    preparedWindDirectionChannel,
    mapActiveTimestampMs,
    mapActiveRatio,
    session.manualWindDirectionDeg,
  ]);
  const mapWindPickerDirectionDeg = Number.isFinite(manualWindDirectionDraftDeg)
    ? normalizeDegrees(manualWindDirectionDraftDeg)
    : Number.isFinite(session.manualWindDirectionDeg)
      ? normalizeDegrees(session.manualWindDirectionDeg)
      : Number.isFinite(mapDisplayedWindDirectionDeg)
        ? normalizeDegrees(mapDisplayedWindDirectionDeg)
        : 0;
  const showManeuverOverlay = mapMarkerOverlayModes.includes("maneuvers");
  const mapOverlayLegends = useMemo(() => {
    const legends = [];

    if (isWindPickerEnabled) {
      legends.push(
        buildMapOverlayLegend("wind", {
          directionLabel: formatDegreesLabel(mapWindPickerDirectionDeg),
        })
      );
    }

    const trackLegend = buildMapOverlayLegend(mapTrackOverlayMode, {
      range:
        mapTrackOverlayMode === "ride-height"
          ? rideHeightOverlayRange
          : speedOverlayRange,
    });
    if (trackLegend) {
      legends.push(trackLegend);
    }

    if (showManeuverOverlay) {
      legends.push(buildMapOverlayLegend("maneuvers"));
    }

    return legends.filter(Boolean);
  }, [
    isWindPickerEnabled,
    mapWindPickerDirectionDeg,
    mapTrackOverlayMode,
    showManeuverOverlay,
    rideHeightOverlayRange,
    speedOverlayRange,
  ]);
  const mapTrailRange = useMemo(
    () =>
      getTrailRange(
        mapReplay.trackPoints,
        preparedTrackPoints,
        trackTrailMode,
        mapActiveTimestampMs,
        mapActiveIndex
      ),
    [
      mapReplay.trackPoints,
      preparedTrackPoints,
      trackTrailMode,
      mapActiveTimestampMs,
      mapActiveIndex,
    ]
  );
  const notesStatusText =
    notesSaveState === "saving"
      ? "Saving..."
      : notesSaveState === "error"
        ? notesErrorMessage || "Could not save notes."
        : notesDraft !== persistedNotesRef.current
        ? "Autosave pending..."
        : "Autosaved";
  const manualWindDirectionStatusText =
    manualWindDirectionSaveState === "saving"
      ? "Saving wind direction..."
      : manualWindDirectionSaveState === "error"
        ? manualWindDirectionErrorMessage || "Could not save manual wind direction."
        : Number.isFinite(session.manualWindDirectionDeg)
          || Number.isFinite(manualWindDirectionDraftDeg)
            ? `Manual wind ${formatDegreesLabel(mapWindPickerDirectionDeg)}`
            : "Drag the center line to set manual wind direction.";
  const races = useMemo(
    () =>
      (baseSession.data?.races ?? []).map((race) =>
        mapPersistedRaceToCard(
          race,
          raceDataByRaceId[race.id] ??
            (race.id === selectedRaceId && raceData ? raceData : null)
        )
      ),
    [baseSession.data?.races, selectedRaceId, raceData, raceDataByRaceId]
  );

  useEffect(() => {
    return () => {
      videoPollRequestRef.current += 1;
    };
  }, []);

  useEffect(() => {
    const availableChannelNames = availableVideoChannels.map((channel) => channel.name);
    setVideoOverlayLayout((currentLayout) => {
      const nextLayout = createEmptyVideoOverlayLayout();

      VIDEO_OVERLAY_POSITION_OPTIONS.forEach((position) => {
        const currentSlots = Array.isArray(currentLayout?.[position])
          ? currentLayout[position]
          : [];
        nextLayout[position] = Array.from(
          { length: VIDEO_OVERLAY_FIELDS_PER_POSITION },
          (_, index) => {
            const value = currentSlots[index] ?? "";
            return availableChannelNames.includes(value) ? value : "";
          }
        );
      });

      if (flattenVideoOverlayLayout(nextLayout).length > 0) {
        return nextLayout;
      }

      return buildDefaultVideoOverlayLayout(availableChannelNames);
    });
  }, [availableVideoChannels]);

  async function handleCreateRace(raceInput) {
    await onSessionRaceCreate(baseSession.id, raceInput);
    setIsRaceWizardOpen(false);
  }

  async function handleUpdateRace(raceInput) {
    if (!editingRace) {
      return;
    }

    await onSessionRaceUpdate(baseSession.id, editingRace.id, raceInput);
    setEditingRace(null);
  }

  async function handleDeleteRace() {
    if (!deletingRace) {
      return;
    }

    setRaceDeleteErrorMessage("");
    setIsDeletingRace(true);

    try {
      await onSessionRaceDelete(baseSession.id, deletingRace.id);
      setDeletingRace(null);
      if (selectedRaceId === deletingRace.id) {
        setActiveTab("races");
      }
    } catch (error) {
      setRaceDeleteErrorMessage(
        error instanceof Error ? error.message : "Unable to delete race."
      );
    } finally {
      setIsDeletingRace(false);
    }
  }

  async function handleRaceSelect(raceId) {
    setLoadingRaceId(raceId);
    try {
      await onSessionRaceSelect(baseSession.id, raceId);
      setActiveTab("overview");
    } finally {
      setLoadingRaceId(null);
    }
  }

  async function handleVideoTrigger() {
    const normalizedFilePath = videoFilePath.trim();
    if (!normalizedFilePath) {
      setVideoTriggerState("error");
      setVideoTriggerMessage("Enter a video file path first.");
      return;
    }
    if (selectedVideoChannels.length === 0) {
      setVideoTriggerState("error");
      setVideoTriggerMessage("Select at least one channel for the video overlay.");
      return;
    }

    setVideoTriggerState("saving");
    setVideoTriggerMessage("Queueing video render...");
    setVideoProgressPercent(0);
    setVideoOutputFilePath("");
    setVideoJobId("");
    const requestId = videoPollRequestRef.current + 1;
    videoPollRequestRef.current = requestId;

    try {
      const job = await onSessionVideoTrigger(
        baseSession.id,
        normalizedFilePath,
        videoOutputFolder.trim(),
        videoOverlayLayout
      );
      if (videoPollRequestRef.current !== requestId) {
        return;
      }

      setVideoJobId(job.jobId);
      setVideoProgressPercent(job.progressPercent ?? 0);
      setVideoTriggerMessage(job.message || "Video render queued...");

      let currentJob = job;
      while (currentJob.status === "queued" || currentJob.status === "running") {
        await delay(VIDEO_PROGRESS_POLL_INTERVAL_MS);
        if (videoPollRequestRef.current !== requestId) {
          return;
        }

        currentJob = await onVideoJobStatusLoad(job.jobId);
        if (videoPollRequestRef.current !== requestId) {
          return;
        }

        setVideoProgressPercent(currentJob.progressPercent ?? 0);
        if (currentJob.message) {
          setVideoTriggerMessage(currentJob.message);
        }
      }

      if (currentJob.status === "completed") {
        setVideoTriggerState("saved");
        setVideoProgressPercent(100);
        setVideoOutputFilePath(currentJob.outputFilePath || "");
        setVideoTriggerMessage(
          currentJob.outputFilePath
            ? `Saved to ${currentJob.outputFilePath}`
            : currentJob.message || "Video render completed."
        );
        return;
      }

      setVideoTriggerState("error");
      setVideoTriggerMessage(currentJob.error || currentJob.message || "Could not render video.");
    } catch (error) {
      setVideoTriggerState("error");
      setVideoTriggerMessage(
        error instanceof Error ? error.message : "Could not trigger video."
      );
    }
  }

  const saveSessionNotes = useEffectEvent(async (nextNotes) => {
    const requestId = latestNotesRequestRef.current + 1;
    latestNotesRequestRef.current = requestId;
    setNotesSaveState("saving");
    setNotesErrorMessage("");

    try {
      const updatedSession = await onSessionNotesChange(baseSession.id, nextNotes);
      if (latestNotesRequestRef.current !== requestId) {
        return;
      }

      persistedNotesRef.current = updatedSession.notes;
      if (latestNotesDraftRef.current !== nextNotes) {
        setNotesSaveState("pending");
        return;
      }

      setNotesDraft(updatedSession.notes);
      setNotesSaveState("saved");
    } catch (error) {
      if (latestNotesRequestRef.current !== requestId) {
        return;
      }

      if (latestNotesDraftRef.current !== nextNotes) {
        setNotesSaveState("pending");
        return;
      }

      setNotesSaveState("error");
      setNotesErrorMessage(
        error instanceof Error ? error.message : "Could not save session notes."
      );
    }
  });

  const saveManualWindDirection = useEffectEvent(async (nextDirectionDeg) => {
    setManualWindDirectionSaveState("saving");
    setManualWindDirectionErrorMessage("");

    try {
      const updatedSession = await onSessionManualWindDirectionChange(
        baseSession.id,
        nextDirectionDeg
      );
      setManualWindDirectionDraftDeg(updatedSession.manualWindDirectionDeg);
      setManualWindDirectionSaveState("saved");
    } catch (error) {
      setManualWindDirectionSaveState("error");
      setManualWindDirectionErrorMessage(
        error instanceof Error ? error.message : "Could not save manual wind direction."
      );
    }
  });

  const syncMapPlaybackToIndex = useEffectEvent((nextIndex) => {
    const boundedIndex = Math.max(
      0,
      Math.min(nextIndex, Math.max(mapReplay.trackPoints.length - 1, 0))
    );

    setIsMapPlaying(false);
    setMapActiveIndex(boundedIndex);
    setMapPlaybackTimestampMs(
      getTrackPointTimestampMs(mapReplay.trackPoints[boundedIndex]) ??
        (mapTrackStartTimestampMs === null
          ? null
          : mapTrackStartTimestampMs +
            (boundedIndex / Math.max(mapReplay.trackPoints.length - 1, 1)) *
              mapDurationSeconds *
              1000)
    );
  });

  useEffect(() => {
    setMapActiveIndex((currentIndex) =>
      Math.min(currentIndex, Math.max(mapReplay.trackPoints.length - 1, 0))
    );
    setMapPlaybackTimestampMs(null);
    setIsMapPlaying(false);
  }, [mapReplay.trackPoints.length]);

  useEffect(() => {
    if (activeTab !== "map" || !isMapPlaying || mapReplay.trackPoints.length < 2) {
      return undefined;
    }

    const playbackStartTimestampMs =
      mapActiveTimestampMs ?? mapTrackStartTimestampMs;
    if (playbackStartTimestampMs === null || mapTrackEndTimestampMs === null) {
      return undefined;
    }

    const playbackStartedAt = window.performance.now();
    const timer = window.setInterval(() => {
      const elapsedMs =
        (window.performance.now() - playbackStartedAt) * mapPlaybackSpeed;
      const nextTimestampMs = Math.min(
        playbackStartTimestampMs + elapsedMs,
        mapTrackEndTimestampMs
      );

      setMapPlaybackTimestampMs(nextTimestampMs);
      setMapActiveIndex(
        preparedTrackPoints.areAllValid
          ? findClosestTimestampIndex(preparedTrackPoints.timestamps, nextTimestampMs)
          : findTrackIndexAtTime(mapReplay.trackPoints, nextTimestampMs)
      );

      if (nextTimestampMs >= mapTrackEndTimestampMs) {
        window.clearInterval(timer);
        setIsMapPlaying(false);
      }
    }, 100);

    return () => window.clearInterval(timer);
  }, [
    activeTab,
    isMapPlaying,
    mapPlaybackSpeed,
    mapReplay.trackPoints,
    preparedTrackPoints,
    mapTrackEndTimestampMs,
    mapTrackStartTimestampMs,
  ]);

  useEffect(() => {
    if (activeTab !== "map") {
      return undefined;
    }

    let snapTimer;

    function snapToMapBoundary() {
      window.clearTimeout(snapTimer);
      snapTimer = window.setTimeout(() => {
        const mapTop = mapTabRef.current?.offsetTop ?? 0;
        const targetScrollY = window.scrollY < mapTop / 2 ? 0 : mapTop;

        window.scrollTo({
          top: targetScrollY,
          behavior: "smooth",
        });
      }, 120);
    }

    window.addEventListener("scroll", snapToMapBoundary, { passive: true });

    return () => {
      window.clearTimeout(snapTimer);
      window.removeEventListener("scroll", snapToMapBoundary);
    };
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== "map") {
      return undefined;
    }

    function handleMapTimelineKeydown(event) {
      if (
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        isEditableElement(event.target)
      ) {
        return;
      }

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        syncMapPlaybackToIndex(mapActiveIndex - 1);
        return;
      }

      if (event.key === "ArrowRight") {
        event.preventDefault();
        syncMapPlaybackToIndex(mapActiveIndex + 1);
      }
    }

    window.addEventListener("keydown", handleMapTimelineKeydown, true);

    return () => {
      window.removeEventListener("keydown", handleMapTimelineKeydown, true);
    };
  }, [activeTab, mapActiveIndex, syncMapPlaybackToIndex]);

  useEffect(() => {
    persistedNotesRef.current = persistedNotes;
    latestNotesRequestRef.current = 0;
    setNotesDraft(persistedNotes);
    setNotesSaveState("saved");
    setNotesErrorMessage("");
  }, [persistedNotes, baseSession.id]);

  useEffect(() => {
    setManualWindDirectionDraftDeg(
      Number.isFinite(persistedManualWindDirectionDeg)
        ? normalizeDegrees(persistedManualWindDirectionDeg)
        : null
    );
    setManualWindDirectionSaveState("saved");
    setManualWindDirectionErrorMessage("");
  }, [persistedManualWindDirectionDeg, baseSession.id]);

  useEffect(() => {
    setVideoFilePath(DEFAULT_VIDEO_FILE_PATH);
    setVideoOutputFolder("");
    setVideoTriggerState("idle");
    setVideoTriggerMessage("");
  }, [baseSession.id]);

  useEffect(() => {
    if (notesDraft === persistedNotesRef.current) {
      return undefined;
    }

    setNotesSaveState("pending");
    const timer = window.setTimeout(() => {
      void saveSessionNotes(notesDraft);
    }, NOTES_AUTOSAVE_DELAY_MS);

    return () => window.clearTimeout(timer);
  }, [notesDraft, saveSessionNotes]);

  useEffect(() => {
    if (activeTab !== "races" || !baseSession.data?.races?.length) {
      return undefined;
    }

    let cancelled = false;
    const unloadedRaces = baseSession.data.races.filter(
      (race) => !raceDataByRaceId[race.id]
    );

    if (unloadedRaces.length === 0) {
      return undefined;
    }

    setLoadingRaceId("all");
    Promise.all(
      unloadedRaces.map((race) => onSessionRaceDataLoad(baseSession.id, race.id))
    )
      .catch(() => {
        // The controller surfaces load failures through the shared error state.
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingRaceId(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    activeTab,
    baseSession.id,
    baseSession.data?.races,
    raceDataByRaceId,
    onSessionRaceDataLoad,
  ]);

  async function handleExport() {
    setIsExporting(true);
    try {
      if (isRaceScoped && selectedRace) {
        await onRaceExport(baseSession.id, selectedRace.id);
        return;
      }

      if (activeTab === "races" && (baseSession.data?.races?.length ?? 0) > 0) {
        await onSessionRacesExport(baseSession.id);
        return;
      }

      await onSessionExport(baseSession.id);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <main
      className={`dashboard-shell${
        activeTab === "map" ? " dashboard-shell--map" : ""
      }`}
    >
      <section className="hero">
        <div className="hero__content">
          <button
            type="button"
            className="back-button"
            onClick={isRaceScoped ? onRaceScopeClear : onBackToBoat}
          >
            <span className="material-icons back-button__icon" aria-hidden="true">
              arrow_back
            </span>
            <span>{isRaceScoped ? "Back to session" : "Back to sessions"}</span>
          </button>
          <h1>{session.title}</h1>
          <p className="hero__subtitle">
            {isRaceScoped
              ? `${boat.name} race segment from ${selectedRace.name}.`
              : `${boat.name} on ${session.dateLabel} in ${session.location}.`}
          </p>
        </div>
        <div className="hero__meta">
          <span className="meta-chip">{boat.name}</span>
          <span className="meta-chip">{boat.className}</span>
          <button
            type="button"
            className="secondary-button"
            onClick={handleExport}
            disabled={isExporting}
          >
            {isExporting
              ? "Exporting..."
              : isRaceScoped
                ? "Export race CSV"
                : activeTab === "races" && (baseSession.data?.races?.length ?? 0) > 0
                  ? "Export races CSV"
                  : "Export to CSV"}
          </button>
        </div>
      </section>

      <nav className="session-tabs" aria-label="Session sections" role="tablist">
        <button
          type="button"
          className={`session-tabs__button${activeTab === "overview" ? " session-tabs__button--active" : ""}`}
          aria-selected={activeTab === "overview"}
          role="tab"
          onClick={() => setActiveTab("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          className={`session-tabs__button${activeTab === "map" ? " session-tabs__button--active" : ""}`}
          aria-selected={activeTab === "map"}
          role="tab"
          onClick={() => setActiveTab("map")}
        >
          Map
        </button>
        <button
          type="button"
          className={`session-tabs__button${activeTab === "charts" ? " session-tabs__button--active" : ""}`}
          aria-selected={activeTab === "charts"}
          role="tab"
          onClick={() => setActiveTab("charts")}
        >
          Charts
        </button>
        <button
          type="button"
          className={`session-tabs__button${activeTab === "races" ? " session-tabs__button--active" : ""}`}
          aria-selected={activeTab === "races"}
          role="tab"
          onClick={() => setActiveTab("races")}
        >
          Races
        </button>
        <button
          type="button"
          className={`session-tabs__button${activeTab === "videos" ? " session-tabs__button--active" : ""}`}
          aria-selected={activeTab === "videos"}
          role="tab"
          onClick={() => setActiveTab("videos")}
        >
          Videos
        </button>
      </nav>

      {activeTab === "overview" ? (
        <div className="session-overview-tab" role="tabpanel" aria-label="Overview">
          <section className="summary-bar summary-bar--detail" aria-label="Session summary">
            <MetricCard label="Duration" value={session.summary.duration} icon={<span className="material-icons">access_time</span>} compact />
            <MetricCard label="Distance" value={session.summary.distance} icon={<span className="material-icons">timeline</span>} compact />
            <MetricCard label="Max speed" value={session.summary.maxSpeed} icon={<span className="material-icons">show_chart</span>} compact />
            <MetricCard label="Foiling avg" value={session.summary.foilingAverage} icon={<span className="material-icons">donut_large</span>} compact />
            <MetricCard label="Tacks" value={session.summary.tacks} icon={<span className="material-icons">sync_alt</span>} compact />
            <MetricCard label="Gybes" value={session.summary.gybes} icon={<span className="material-icons">autorenew</span>} compact />
          </section>

          <section className="dashboard-panel conditions-panel">
            <div className="section-heading section-heading--stacked">
              <div>
                <h2>Conditions</h2>
              </div>
            </div>
            <div className="conditions-groups">
              {session.conditions.map((conditionGroup) => (
                <div key={conditionGroup.title} className="conditions-group">
                  <p className="conditions-group__title">{conditionGroup.title}</p>
                  <div className="conditions-list conditions-list--row">
                    {conditionGroup.items.map((item) => (
                      <div key={`${conditionGroup.title}-${item.label}`} className="condition-row">
                        <span className="material-icons" aria-hidden="true">{item.icon}</span>
                        <div>
                          <p className="condition-row__label">{item.label}</p>
                          <strong>{item.value}</strong>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="performance-row" aria-label="Performance split">
            <RingChart chart={session.foilingChart} />
            <RingChart chart={session.foilingTackChart} />
            <RingChart chart={session.foilingGybeChart} />
          </section>
        </div>
      ) : activeTab === "map" ? (
        <section
          ref={mapTabRef}
          className="session-map-tab"
          aria-label={isRaceScoped ? "Race map view" : "Session map view"}
          role="tabpanel"
        >
            <div className="session-map-tab__main">
              <MapLibreTrackMapCanvas
                replay={mapReplay}
                activeIndex={mapActiveIndex}
                trailRange={mapTrailRange}
                trackOverlayMode={mapTrackOverlayMode}
                showManeuvers={showManeuverOverlay}
                showWindPicker={isWindPickerEnabled}
                windDirectionDeg={mapDisplayedWindDirectionDeg}
                editableWindDirectionDeg={mapWindPickerDirectionDeg}
                foilingChannel={foilingChannel}
                maneuverEvents={mapEvents}
                maneuverTrackPoints={maneuverTrackPoints}
                speedChannel={speedChannel}
                speedRange={speedOverlayRange}
                rideHeightChannel={rideHeightChannel}
                rideHeightRange={rideHeightOverlayRange}
                turnRateChannel={turnRateChannel}
                turnRateRange={turnRateOverlayRange}
                onWindDirectionChange={(nextDirectionDeg) => {
                  setManualWindDirectionDraftDeg(normalizeDegrees(nextDirectionDeg));
                }}
                onWindDirectionCommit={(nextDirectionDeg) => {
                  const normalizedDirectionDeg = normalizeDegrees(nextDirectionDeg);
                  setManualWindDirectionDraftDeg(normalizedDirectionDeg);
                  void saveManualWindDirection(normalizedDirectionDeg);
                }}
                className="session-map-tab__canvas"
                ariaLabel={isRaceScoped ? "Race track map" : "Full session track map"}
                showActiveMarker
              />
              {mapOverlayLegends.length > 0 && mapReplay.trackPoints.length > 1 && (
                <div className="session-map-overlay-legends">
                  {mapOverlayLegends.map((legend) => (
                    <div
                      key={`${legend.type}-${legend.title}`}
                      className="session-map-overlay-legend"
                      aria-label={legend.title}
                    >
                      <p className="session-map-overlay-legend__title">{legend.title}</p>
                      {legend.type === "foiling" ? (
                        <div className="session-map-overlay-legend__swatches">
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--foiling" />
                            Foiling
                          </span>
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--no-foiling" />
                            No foiling
                          </span>
                        </div>
                      ) : legend.type === "wind" ? (
                        <div className="session-map-overlay-legend__swatches">
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--wind" />
                            Picker angle {legend.directionLabel}
                          </span>
                        </div>
                      ) : legend.type === "maneuvers" ? (
                        <div className="session-map-overlay-legend__swatches">
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--tack" />
                            Tack
                          </span>
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--gybe" />
                            Gybe
                          </span>
                          <span className="session-map-overlay-legend__item">
                            <span className="session-map-overlay-legend__swatch session-map-overlay-legend__swatch--foiling-maneuver" />
                            Foiling ring
                          </span>
                        </div>
                      ) : (
                        <div className="session-map-overlay-legend__speed">
                          <div
                            className={`session-map-overlay-legend__gradient${
                              legend.type === "turn-rate"
                                ? " session-map-overlay-legend__gradient--turn-rate"
                                : ""
                            }`}
                            aria-hidden="true"
                          />
                          <div className="session-map-overlay-legend__labels">
                            <span>{legend.minLabel}</span>
                            {legend.centerLabel ? <span>{legend.centerLabel}</span> : null}
                            <span>{legend.maxLabel}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {mapReplay.trackPoints.length === 0 && (
                <div className="track-map__empty">
                  <span className="material-icons" aria-hidden="true">route</span>
                  <p>
                    No latitude/longitude track is available for this{" "}
                    {isRaceScoped ? "race" : "session"} yet.
                  </p>
                </div>
              )}
              <div className="session-map-controls">
                <button
                  type="button"
                  className="session-map-controls__button"
                  disabled={!hasMapReplay}
                  onClick={() => {
                    if (!hasMapReplay) {
                      return;
                    }

                    if (
                      mapTrackEndTimestampMs !== null &&
                      mapActiveTimestampMs !== null &&
                      mapActiveTimestampMs >= mapTrackEndTimestampMs
                    ) {
                      setMapActiveIndex(0);
                      setMapPlaybackTimestampMs(mapTrackStartTimestampMs);
                    }

                    setIsMapPlaying((currentValue) => !currentValue);
                  }}
                >
                  <span className="material-icons" aria-hidden="true">
                    {isMapPlaying ? "pause" : "play_arrow"}
                  </span>
                </button>

                <span className="session-map-controls__time">
                  {mapActivePoint ? formatPlaybackTime(mapDisplayedActiveSeconds) : "No track"}
                </span>
                <input
                  className="session-map-controls__range"
                  type="range"
                  min="0"
                  max={Math.max(mapReplay.trackPoints.length - 1, 0)}
                  value={Math.min(
                    mapActiveIndex,
                    Math.max(mapReplay.trackPoints.length - 1, 0)
                  )}
                  disabled={!hasMapReplay}
                  onChange={(event) => {
                    const nextIndex = Number(event.target.value);
                    setIsMapPlaying(false);
                    setMapActiveIndex(nextIndex);
                    setMapPlaybackTimestampMs(
                      getTrackPointTimestampMs(mapReplay.trackPoints[nextIndex]) ??
                        (mapTrackStartTimestampMs === null
                          ? null
                          : mapTrackStartTimestampMs +
                            (nextIndex /
                              Math.max(mapReplay.trackPoints.length - 1, 1)) *
                              mapDurationSeconds *
                              1000)
                    );
                  }}
                />
                <span className="session-map-controls__time">
                  {formatPlaybackTime(mapDurationSeconds)}
                </span>
                <div className="session-map-controls__speeds" aria-label="Playback speed">
                  {PLAYBACK_SPEEDS.map((speed) => (
                    <button
                      key={speed}
                      type="button"
                      className={`session-map-controls__speed${
                        mapPlaybackSpeed === speed ? " session-map-controls__speed--active" : ""
                      }`}
                      onClick={() => setMapPlaybackSpeed(speed)}
                    >
                      {speed}x
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="session-map-controls__settings"
                  aria-label="Map settings"
                  onClick={() => {
                    setMapSettingsSection("overlays");
                    setIsMapSettingsOpen(true);
                  }}
                >
                  <span className="material-icons" aria-hidden="true">settings</span>
                </button>
              </div>
              <p
                className={`session-map-controls__status${
                  manualWindDirectionSaveState === "error"
                    ? " session-map-controls__status--error"
                    : ""
                }`}
              >
                {manualWindDirectionStatusText}
              </p>
            </div>
            <aside
              className="session-map-tab__side"
              aria-label={isRaceScoped ? "Race channel data" : "Session channel data"}
            >
              <div className="session-map-data-list">
                <MapDataField
                  channel={{ name: "UTC", unit: "" }}
                  value={formatUtcTime(mapActiveTimestampMs)}
                />
                {preparedRelativeTimeChannel && (
                  <MapDataField
                    channel={preparedRelativeTimeChannel}
                    value={findChannelValueAtTime(
                      preparedRelativeTimeChannel,
                      mapActiveTimestampMs,
                      mapActiveRatio
                    )}
                  />
                )}
                {preparedRideHeightChannel && (
                  <MapDataField
                    channel={preparedRideHeightChannel}
                    value={findChannelValueAtTime(
                      preparedRideHeightChannel,
                      mapActiveTimestampMs,
                      mapActiveRatio
                    )}
                  />
                )}
                {preparedMapChannelsWithoutRelativeTime.map((channel) => (
                  <MapDataField
                    key={channel.id}
                    channel={channel}
                    value={findChannelValueAtTime(
                      channel,
                      mapActiveTimestampMs,
                      mapActiveRatio
                    )}
                  />
                ))}
                {mapChannels.length === 0 && (
                  <p className="session-map-data-list__empty">
                    No channel data is available for this {isRaceScoped ? "race" : "session"}.
                  </p>
                )}
              </div>
            </aside>
            {isMapSettingsOpen && (
              <div className="map-settings-overlay" role="presentation">
                <section
                  className="map-settings-wizard"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="map-settings-title"
                >
                  <div className="wizard-header">
                    <div>
                      <p className="eyebrow">Map settings</p>
                      <h2 id="map-settings-title">Display options</h2>
                    </div>
                    <button
                      type="button"
                      className="ghost-button"
                      onClick={() => setIsMapSettingsOpen(false)}
                    >
                      Close
                    </button>
                  </div>
                  <div className="map-settings-wizard__body">
                    <aside
                      className="map-settings-wizard__sidebar"
                      aria-label="Map settings sections"
                    >
                      <button
                        type="button"
                        className={`map-settings-wizard__nav${
                          mapSettingsSection === "overlays"
                            ? " map-settings-wizard__nav--active"
                            : ""
                        }`}
                        onClick={() => setMapSettingsSection("overlays")}
                      >
                        Overlays
                      </button>
                      <button
                        type="button"
                        className={`map-settings-wizard__nav${
                          mapSettingsSection === "track"
                            ? " map-settings-wizard__nav--active"
                            : ""
                        }`}
                        onClick={() => setMapSettingsSection("track")}
                      >
                        Track
                      </button>
                      <button
                        type="button"
                        className={`map-settings-wizard__nav${
                          mapSettingsSection === "wind"
                            ? " map-settings-wizard__nav--active"
                            : ""
                        }`}
                        onClick={() => setMapSettingsSection("wind")}
                      >
                        Wind
                      </button>
                    </aside>
                    <div className="map-settings-wizard__content">
                      {mapSettingsSection === "overlays" && (
                        <div className="map-settings-groups">
                          <fieldset
                            className="map-settings-fieldset"
                            aria-label="Track overlay options"
                          >
                            <legend>Track overlay</legend>
                            {MAP_TRACK_OVERLAY_OPTIONS.map((option) => (
                              <label key={option.value} className="map-settings-radio">
                                <input
                                  type="radio"
                                  name="mapTrackOverlayMode"
                                  value={option.value}
                                  checked={mapTrackOverlayMode === option.value}
                                  onChange={() => setMapTrackOverlayMode(option.value)}
                                />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </fieldset>
                          <fieldset
                            className="map-settings-fieldset"
                            aria-label="Marker overlay options"
                          >
                            <legend>Marker overlays</legend>
                            {MAP_MARKER_OVERLAY_OPTIONS.map((option) => (
                              <label key={option.value} className="map-settings-radio">
                                <input
                                  type="checkbox"
                                  checked={mapMarkerOverlayModes.includes(option.value)}
                                  onChange={() => {
                                    setMapMarkerOverlayModes((currentModes) =>
                                      currentModes.includes(option.value)
                                        ? currentModes.filter((mode) => mode !== option.value)
                                        : [...currentModes, option.value]
                                    );
                                  }}
                                />
                                <span>{option.label}</span>
                              </label>
                            ))}
                          </fieldset>
                        </div>
                      )}
                      {mapSettingsSection === "track" && (
                        <fieldset className="map-settings-fieldset">
                          <legend>Track trail</legend>
                          {TRACK_TRAIL_OPTIONS.map((option) => (
                            <label key={option.value} className="map-settings-radio">
                              <input
                                type="radio"
                                name="trackTrailMode"
                                value={option.value}
                                checked={trackTrailMode === option.value}
                                onChange={() => setTrackTrailMode(option.value)}
                              />
                              <span>{option.label}</span>
                            </label>
                          ))}
                        </fieldset>
                      )}
                      {mapSettingsSection === "wind" && (
                        <fieldset className="map-settings-fieldset" aria-label="Wind picker">
                          <legend>Wind picker</legend>
                          <label className="map-settings-radio">
                            <input
                              type="checkbox"
                              checked={isWindPickerEnabled}
                              onChange={() =>
                                setIsWindPickerEnabled((currentValue) => !currentValue)
                              }
                            />
                            <span>Show wind picker on the map</span>
                          </label>
                        </fieldset>
                      )}
                    </div>
                  </div>
                </section>
              </div>
            )}
        </section>
      ) : activeTab === "charts" ? (
        <section className="session-charts-tab" aria-label="Session charts" role="tabpanel">
          <TimeSeriesChart
            title="SOG vs inferred SOG"
            unit={sogChannel?.unit || inferredSogChannel?.unit || "kn"}
            series={[
              {
                label: "SOG",
                unit: sogChannel?.unit ?? "kn",
                values: sogChannel?.values ?? [],
                color: "#0f766e",
              },
              {
                label: "Inferred SOG",
                unit: inferredSogChannel?.unit ?? "kn",
                values: inferredSogChannel?.values ?? [],
                color: "#f08c3a",
              },
            ]}
          />
          {hasWindSeries && (
            <>
              <TimeSeriesChart
                title="Wind speed & gusts"
                unit={windSpeedChannel?.unit || windGustChannel?.unit || "m/s"}
                series={[
                  {
                    label: "Wind speed",
                    unit: windSpeedChannel?.unit ?? "m/s",
                    values: windSpeedChannel?.values ?? [],
                    color: "#1f4f7a",
                  },
                  {
                    label: "Gusts",
                    unit: windGustChannel?.unit ?? "m/s",
                    values: windGustChannel?.values ?? [],
                    color: "#b45309",
                  },
                ]}
              />
              <TimeSeriesChart
                title="Wind direction"
                unit={windDirectionChannel?.unit ?? "deg"}
                values={windDirectionChannel?.values ?? []}
              />
            </>
          )}
          <TimeSeriesChart
            title="HR"
            unit={heartRateChannel?.unit ?? "bpm"}
            values={heartRateChannel?.values ?? []}
          />
        </section>
      ) : activeTab === "races" ? (
        <section
          className="dashboard-panel session-races-tab"
          aria-label="Session races"
          role="tabpanel"
        >
          <div className="section-heading">
            <div>
              <h2>Races</h2>
              <p className="body-copy">
                Add starts here and open a race to inspect the same views with race-scoped data.
              </p>
            </div>
            <div className="section-heading__actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => setIsRaceWizardOpen(true)}
              >
                Add race
              </button>
            </div>
          </div>

          <div className="race-list">
            {races.length === 0 ? (
              <p className="session-map-data-list__empty">
                No races have been added to this session yet.
              </p>
            ) : (
              races.map((race) => (
                <RaceCard
                  key={race.id}
                  race={race}
                  isActive={race.id === selectedRaceId}
                  isLoading={
                    loadingRaceId === race.id ||
                    (loadingRaceId === "all" && !raceDataByRaceId[race.id])
                  }
                  onSelect={handleRaceSelect}
                  onEdit={() => setEditingRace(race)}
                  onDelete={() => {
                    setRaceDeleteErrorMessage("");
                    setDeletingRace(race);
                  }}
                />
              ))
            )}
          </div>
        </section>
      ) : (
        <section
          className="dashboard-panel session-videos-tab"
          aria-label="Session videos"
          role="tabpanel"
        >
          <div className="section-heading section-heading--stacked">
            <div>
              <p className="eyebrow">Video</p>
              <h2>Trigger video processing</h2>
              <p className="body-copy">
                Send the current session id together with a video file path to the backend.
                Leave the output folder blank to save into Downloads.
              </p>
            </div>
          </div>

          <label className="session-videos-tab__field">
            <span className="session-videos-tab__label">Video file path</span>
            <input
              className="session-videos-tab__input"
              type="text"
              value={videoFilePath}
              onChange={(event) => {
                setVideoFilePath(event.target.value);
                if (videoTriggerState !== "idle") {
                  setVideoTriggerState("idle");
                  setVideoTriggerMessage("");
                  setVideoProgressPercent(0);
                  setVideoOutputFilePath("");
                  setVideoJobId("");
                }
              }}
              placeholder={DEFAULT_VIDEO_FILE_PATH}
            />
          </label>

          <label className="session-videos-tab__field">
            <span className="session-videos-tab__label">Output folder</span>
            <input
              className="session-videos-tab__input"
              type="text"
              value={videoOutputFolder}
              onChange={(event) => {
                setVideoOutputFolder(event.target.value);
                if (videoTriggerState !== "idle") {
                  setVideoTriggerState("idle");
                  setVideoTriggerMessage("");
                  setVideoProgressPercent(0);
                  setVideoOutputFilePath("");
                  setVideoJobId("");
                }
              }}
              placeholder={DEFAULT_VIDEO_OUTPUT_FOLDER}
            />
          </label>

          <div className="session-videos-tab__field">
            <span className="session-videos-tab__label">Text placement</span>
            {availableVideoChannels.length > 0 ? (
              <div className="session-videos-tab__position-grid">
                {VIDEO_OVERLAY_POSITION_OPTIONS.map((position) => (
                  <section key={position} className="session-videos-tab__position-card">
                    <div className="session-videos-tab__position-card-header">
                      <span className="session-videos-tab__position-card-title">
                        {position}
                      </span>
                      <span className="session-videos-tab__position-card-meta">
                        {VIDEO_OVERLAY_FIELDS_PER_POSITION} fields
                      </span>
                    </div>
                    <div className="session-videos-tab__slot-list">
                      {Array.from(
                        { length: VIDEO_OVERLAY_FIELDS_PER_POSITION },
                        (_, slotIndex) => (
                          <label
                            key={`${position}-${slotIndex}`}
                            className="session-videos-tab__slot-field"
                          >
                            <span className="session-videos-tab__slot-label">
                              {position} {slotIndex + 1}
                            </span>
                            <select
                              value={videoOverlayLayout[position]?.[slotIndex] ?? ""}
                              onChange={(event) => {
                                const nextValue = event.target.value;
                                setVideoOverlayLayout((currentLayout) => {
                                  const nextLayout = {
                                    ...currentLayout,
                                    [position]: [...(currentLayout[position] ?? [])],
                                  };
                                  nextLayout[position][slotIndex] = nextValue;
                                  return nextLayout;
                                });
                              }}
                            >
                              <option value="">None</option>
                              {availableVideoChannels.map((channel) => (
                                <option key={channel.id} value={channel.name}>
                                  {formatChannelOverlayLabel(channel)}
                                </option>
                              ))}
                            </select>
                          </label>
                        )
                      )}
                    </div>
                  </section>
                ))}
              </div>
            ) : (
              <p className="session-videos-tab__helper">
                No session channels are available for video overlay.
              </p>
            )}
          </div>

          <button
            type="button"
            className="session-videos-tab__trigger"
            disabled={videoTriggerState === "saving"}
            onClick={() => {
              void handleVideoTrigger();
            }}
          >
            {videoTriggerState === "saving" ? "Processing..." : "Trigger"}
          </button>

          {videoTriggerState === "saving" || videoTriggerState === "saved" ? (
            <div className="session-videos-tab__progress" aria-live="polite">
              <div className="session-videos-tab__progress-track" aria-hidden="true">
                <div
                  className="session-videos-tab__progress-fill"
                  style={{ width: `${Math.max(0, Math.min(videoProgressPercent, 100))}%` }}
                />
              </div>
              <div className="session-videos-tab__progress-meta">
                <span>{Math.round(videoProgressPercent)}%</span>
                {videoJobId ? <span>Job {videoJobId.slice(0, 8)}</span> : null}
              </div>
            </div>
          ) : null}

          <p
            className={`session-videos-tab__status${
              videoTriggerState === "error"
                ? " session-videos-tab__status--error"
                : videoTriggerState === "saved"
                  ? " session-videos-tab__status--success"
                  : ""
            }`}
            aria-live="polite"
          >
            {videoTriggerMessage
              || (videoTriggerState === "saving"
                ? "Rendering video..."
                : "Idle")}
          </p>

          {videoOutputFilePath ? (
            <p className="session-videos-tab__output-path">
              Output: {videoOutputFilePath}
            </p>
          ) : null}
        </section>
      )}

      {isRaceWizardOpen && (
        <RaceWizardModal
          raceNumber={races.length + 1}
          replay={baseSession.replay}
          onClose={() => setIsRaceWizardOpen(false)}
          onSubmit={handleCreateRace}
        />
      )}

      {editingRace && (
        <RaceFormModal
          race={editingRace}
          replay={baseSession.replay}
          onClose={() => setEditingRace(null)}
          onSubmit={handleUpdateRace}
        />
      )}

      {deletingRace && (
        <div className="wizard-overlay" role="presentation">
          <section
            className="wizard-modal race-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="race-delete-title"
          >
            <header className="wizard-header">
              <div>
                <h3 id="race-delete-title">Delete {deletingRace.name}</h3>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => setDeletingRace(null)}
                disabled={isDeletingRace}
              >
                Cancel
              </button>
            </header>

            <p className="body-copy race-delete-modal__copy">
              This removes the race segment from this session.
            </p>

            {raceDeleteErrorMessage && <p className="wizard-error">{raceDeleteErrorMessage}</p>}

            <footer className="wizard-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setDeletingRace(null)}
                disabled={isDeletingRace}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteRace}
                disabled={isDeletingRace}
              >
                {isDeletingRace ? "Deleting..." : "Delete race"}
              </button>
            </footer>
          </section>
        </div>
      )}

      {activeTab === "overview" && (
        <>
          <TrackReplayCard
            replay={session.replay}
            sessionTitle={session.title}
            showControls={false}
          />
          {!isRaceScoped && (
            <section className="dashboard-panel session-notes-panel" aria-label="Session notes">
            <div className="section-heading">
              <div>
                <h2>Session notes</h2>
                <p className="body-copy">
                  Capture observations here. Changes save automatically when you pause typing.
                </p>
              </div>
              <p
                className={`session-notes-panel__status${
                  notesSaveState === "error"
                    ? " session-notes-panel__status--error"
                    : ""
                }`}
                aria-live="polite"
              >
                {notesStatusText}
              </p>
            </div>
            <textarea
              className="session-notes-panel__input"
              value={notesDraft}
              onChange={(event) => setNotesDraft(event.target.value)}
              placeholder="Add debrief notes, setup changes, what worked, and what to revisit next time."
            />
            </section>
          )}
        </>
      )}
    </main>
  );
}
