const BOAT_IMAGE_BY_NAME = {
  sips: "/assets/boat-aurora.svg",
  "herr nielson": "/assets/boat-northwind.svg",
  "northwind 36": "/assets/boat-northwind.svg",
  "stormbird 40": "/assets/boat-stormbird.svg",
};

const FALLBACK_BOAT_IMAGES = [
  "/assets/boat-aurora.svg",
  "/assets/boat-northwind.svg",
  "/assets/boat-stormbird.svg",
];

function getApiBaseUrl() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;
  if (typeof apiBaseUrl === "string" && apiBaseUrl.trim()) {
    return apiBaseUrl.trim().replace(/\/+$/, "");
  }

  return null;
}

function getDashboardOverviewEndpoint() {
  const endpointOverride = import.meta.env.VITE_DASHBOARD_OVERVIEW_ENDPOINT;
  if (typeof endpointOverride === "string" && endpointOverride.trim()) {
    return endpointOverride.trim();
  }

  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    return `${apiBaseUrl}/dashboard/overview`;
  }

  return "/dashboard/overview";
}

function getSessionsEndpoint() {
  const endpointOverride = import.meta.env.VITE_SESSIONS_ENDPOINT;
  if (typeof endpointOverride === "string" && endpointOverride.trim()) {
    return endpointOverride.trim();
  }

  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions`;
  }

  return "/sessions";
}

function getSessionDataEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/data`;
  }

  return `/sessions/${encodedSessionId}/data`;
}

function getSessionEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}`;
  }

  return `/sessions/${encodedSessionId}`;
}

function getSessionExportEndpoint(sessionId, extension) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/export.${extension}`;
  }

  return `/sessions/${encodedSessionId}/export.${extension}`;
}

function getSessionNotesEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/notes`;
  }

  return `/sessions/${encodedSessionId}/notes`;
}

function getSessionManualWindDirectionEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/manual-wind-direction`;
  }

  return `/sessions/${encodedSessionId}/manual-wind-direction`;
}

function getSessionVideoEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/video`;
  }

  return `/sessions/${encodedSessionId}/video`;
}

function getJobEndpoint(jobId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedJobId = encodeURIComponent(jobId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/jobs/${encodedJobId}`;
  }

  return `/jobs/${encodedJobId}`;
}

function getSessionRacesEndpoint(sessionId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/races`;
  }

  return `/sessions/${encodedSessionId}/races`;
}

function getSessionRaceEndpoint(sessionId, raceId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  const encodedRaceId = encodeURIComponent(raceId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/races/${encodedRaceId}`;
  }

  return `/sessions/${encodedSessionId}/races/${encodedRaceId}`;
}

function getSessionRaceDataEndpoint(sessionId, raceId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  const encodedRaceId = encodeURIComponent(raceId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/races/${encodedRaceId}/data`;
  }

  return `/sessions/${encodedSessionId}/races/${encodedRaceId}/data`;
}

function getSessionRaceExportEndpoint(sessionId, raceId, extension) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  const encodedRaceId = encodeURIComponent(raceId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/races/${encodedRaceId}/export.${extension}`;
  }

  return `/sessions/${encodedSessionId}/races/${encodedRaceId}/export.${extension}`;
}

function getSessionRacesExportEndpoint(sessionId, extension) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedSessionId = encodeURIComponent(sessionId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/sessions/${encodedSessionId}/races/export.${extension}`;
  }

  return `/sessions/${encodedSessionId}/races/export.${extension}`;
}

function getBoatExportEndpoint(boatId, extension) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedBoatId = encodeURIComponent(boatId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/boats/${encodedBoatId}/export.${extension}`;
  }

  return `/boats/${encodedBoatId}/export.${extension}`;
}

function getBoatsEndpoint() {
  const apiBaseUrl = getApiBaseUrl();
  if (apiBaseUrl) {
    return `${apiBaseUrl}/boats`;
  }

  return "/boats";
}

function getBoatEndpoint(boatId) {
  const apiBaseUrl = getApiBaseUrl();
  const encodedBoatId = encodeURIComponent(boatId);
  if (apiBaseUrl) {
    return `${apiBaseUrl}/boats/${encodedBoatId}`;
  }

  return `/boats/${encodedBoatId}`;
}

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toNullableNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDateLabel(value) {
  if (!value) {
    return "Unknown date";
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return "Unknown date";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsedDate);
}

function buildSessionWindow(sessions) {
  const validDates = sessions
    .map((session) => session.start_at ?? session.end_at)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((a, b) => a.getTime() - b.getTime());

  if (validDates.length === 0) {
    return "Database overview";
  }

  const formatter = new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const startLabel = formatter.format(validDates[0]);
  const endLabel = formatter.format(validDates[validDates.length - 1]);
  return startLabel === endLabel ? startLabel : `${startLabel} to ${endLabel}`;
}

function degreesToCompass(degreesInput) {
  const degrees = toNumber(degreesInput, NaN);
  if (!Number.isFinite(degrees)) {
    return "N";
  }

  const normalized = ((degrees % 360) + 360) % 360;
  const sectors = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
  ];

  const index = Math.round(normalized / 22.5) % sectors.length;
  return sectors[index];
}

function resolveBoatImage(boatName, index) {
  const normalizedName = String(boatName || "")
    .trim()
    .toLowerCase();
  if (normalizedName in BOAT_IMAGE_BY_NAME) {
    return BOAT_IMAGE_BY_NAME[normalizedName];
  }

  return FALLBACK_BOAT_IMAGES[index % FALLBACK_BOAT_IMAGES.length];
}

function mapTrackPoints(trackPoints) {
  if (!Array.isArray(trackPoints)) {
    return [];
  }

  return trackPoints
    .map((point) => {
      const latitude = toNumber(point.latitude ?? point.lat, NaN);
      const longitude = toNumber(point.longitude ?? point.lon, NaN);

      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return null;
      }

      return {
        latitude,
        longitude,
        timestamp: point.timestamp ?? point.time ?? null,
      };
    })
    .filter(Boolean);
}

function mapSessionNotes(notes) {
  return typeof notes === "string" ? notes : "";
}

function countSessionDataEvents(sessionData, names) {
  if (!sessionData || !Array.isArray(sessionData.events)) {
    return 0;
  }

  return sessionData.events.filter((event) =>
    names.includes(String(event.event_type ?? "").toLowerCase())
  ).length;
}

function mapSession(session) {
  const location =
    typeof session.location === "string" && session.location.trim()
      ? session.location.trim()
      : "Unknown location";
  const windStrengthKts = Math.max(0, Math.round(toNumber(session.wind_speed_kts, 0)));
  const gustsKts = Math.max(0, Math.round(toNumber(session.wind_gust_kts, windStrengthKts)));
  const windDirectionDeg = ((Math.round(toNumber(session.wind_direction_deg, 0)) % 360) + 360) % 360;
  const waveHeightM = Math.max(0, toNumber(session.wave_height_m, 0));
  const manualWindStrengthKts = toNullableNumber(session.manual_wind_speed_kts);
  const manualGustsKts = toNullableNumber(session.manual_wind_gust_kts);
  const manualWindDirectionDeg = toNullableNumber(session.manual_wind_direction_deg);
  const manualWaveHeightM = toNullableNumber(session.manual_wave_height_m);
  const externalWindStrengthKts = toNullableNumber(session.external_wind_speed_kts);
  const externalGustsKts = toNullableNumber(session.external_wind_gust_kts);
  const externalWindDirectionDeg = toNullableNumber(session.external_wind_direction_deg);
  const foilingPercent = Math.max(0, toNumber(session.foiling_percentage, 0));
  const foilingTimeMin = Math.max(0, toNumber(session.foiling_time_min, 0));
  const tacks = Math.max(0, Math.round(toNumber(session.tack_count, 0)));
  const gybes = Math.max(0, Math.round(toNumber(session.gybe_count, 0)));
  const foilingTacks = Math.max(0, Math.round(toNumber(session.foiling_tack_count, 0)));
  const foilingGybes = Math.max(0, Math.round(toNumber(session.foiling_gybe_count, 0)));
  const foilingTackPercentage = Math.max(0, toNumber(session.foiling_tack_percentage, 0));
  const foilingGybePercentage = Math.max(0, toNumber(session.foiling_gybe_percentage, 0));

  return {
    id: String(session.id),
    title:
      typeof session.name === "string" && session.name.trim()
        ? session.name.trim()
        : "Unnamed session",
    dateLabel: formatDateLabel(session.start_at ?? session.end_at),
    location,
    durationHours: Math.max(0, toNumber(session.duration_hours, 0)),
    distanceNm: Math.max(0, toNumber(session.distance_nm, 0)),
    maxSpeedKts: Math.max(0, toNumber(session.max_speed_kts, 0)),
    windStrengthKts,
    gustsKts,
    windDirection: degreesToCompass(windDirectionDeg),
    windDirectionDeg,
    waveHeightM,
    manualWindStrengthKts,
    manualGustsKts,
    manualWindDirectionDeg,
    manualWaveHeightM,
    externalWindStrengthKts,
    externalGustsKts,
    externalWindDirectionDeg,
    notes: mapSessionNotes(session.notes),
    foilingPercent,
    foilingTimeMin,
    capsizes: 0,
    tacks,
    gybes,
    foilingTacks,
    foilingGybes,
    foilingTackPercentage,
    foilingGybePercentage,
    trackPoints: mapTrackPoints(session.track_points),
  };
}

function mapBoat(boat, sessions, index) {
  return {
    id: String(boat.id),
    name:
      typeof boat.name === "string" && boat.name.trim()
        ? boat.name.trim()
        : "Unknown boat",
    image: resolveBoatImage(boat.name, index),
    hours: Math.max(0, toNumber(boat.total_hours, 0)),
    distanceNm: Math.max(0, toNumber(boat.total_distance_nm, 0)),
    className:
      typeof boat.class_name === "string" && boat.class_name.trim()
        ? boat.class_name.trim()
        : "Unknown class",
    sailNumber:
      typeof boat.sailnumber === "string" && boat.sailnumber.trim()
        ? boat.sailnumber.trim()
        : "",
    sessions,
  };
}

function mapDashboardOverviewToSailingSession(overview) {
  const overviewBoats = Array.isArray(overview.boats) ? overview.boats : [];
  const overviewSessions = Array.isArray(overview.sessions) ? overview.sessions : [];

  const sessionsByBoatId = new Map();
  for (const session of overviewSessions) {
    const boatId = session.boat_id ? String(session.boat_id) : null;
    if (!boatId) {
      continue;
    }

    const mappedSession = mapSession(session);
    const sessions = sessionsByBoatId.get(boatId) ?? [];
    sessions.push(mappedSession);
    sessionsByBoatId.set(boatId, sessions);
  }

  const boats = overviewBoats.map((boat, index) =>
    mapBoat(boat, sessionsByBoatId.get(String(boat.id)) ?? [], index)
  );

  const sailorNameInput = import.meta.env.VITE_SAILOR_NAME;
  const sailorName =
    typeof sailorNameInput === "string" && sailorNameInput.trim()
      ? sailorNameInput.trim()
      : "Sailing Insights";

  return {
    sailorName,
    sessionWindow: buildSessionWindow(overviewSessions),
    boats,
  };
}

async function readErrorMessage(response, fallbackMessage) {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      const payload = await response.json();
      if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
        return payload.detail.trim();
      }
    } catch {
      return fallbackMessage;
    }
  }

  try {
    const errorText = await response.text();
    if (errorText.trim()) {
      return errorText;
    }
  } catch {
    return fallbackMessage;
  }

  return fallbackMessage;
}

function getDownloadFilename(response, fallbackFilename) {
  const contentDisposition = response.headers.get("content-disposition") || "";
  const match = contentDisposition.match(/filename=\"?([^"]+)\"?/i);
  return match?.[1] || fallbackFilename;
}

async function downloadEndpointFile(endpoint, fallbackFilename, fallbackErrorMessage) {
  let response;
  try {
    response = await fetch(endpoint);
  } catch {
    throw new Error(fallbackErrorMessage);
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not download file (${response.status}).`
    );
    throw new Error(errorText);
  }

  const blob = await response.blob();
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = getDownloadFilename(response, fallbackFilename);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(downloadUrl);
}

export async function getSailingSession() {
  let response;
  try {
    response = await fetch(getDashboardOverviewEndpoint());
  } catch {
    throw new Error(
      "Dashboard API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not load dashboard data (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Dashboard endpoint did not return JSON.");
  }

  const overview = await response.json();
  return mapDashboardOverviewToSailingSession(overview);
}

function mapSessionDataValue(value) {
  return {
    timestamp: value.timestamp,
    value: value.value,
  };
}

function mapSessionDataChannel(channel) {
  return {
    id: String(channel.id),
    name: channel.name,
    unit: channel.unit ?? "",
    source: channel.source ?? "",
    isDerived: Boolean(channel.is_derived),
    dataType: channel.data_type,
    values: Array.isArray(channel.values)
      ? channel.values.map(mapSessionDataValue)
      : [],
  };
}

function mapSessionDataEvent(event) {
  return {
    id: String(event.id),
    event_type: event.event_type,
    start_time: event.start_time ?? null,
    end_time: event.end_time ?? null,
    source: event.source ?? "",
    confidence:
      typeof event.confidence === "number" && Number.isFinite(event.confidence)
        ? event.confidence
        : null,
    foiling: Boolean(event.foiling),
    latitude: toNullableNumber(event.latitude),
    longitude: toNullableNumber(event.longitude),
  };
}

function mapSessionRace(race) {
  return {
    id: String(race.id),
    sessionId: String(race.session_id),
    name:
      typeof race.name === "string" && race.name.trim()
        ? race.name.trim()
        : "Unnamed race",
    startTime: race.start_time,
    endTime: race.finish_time,
  };
}

export async function getSessionData(sessionId) {
  let response;
  try {
    response = await fetch(getSessionDataEndpoint(sessionId));
  } catch {
    throw new Error(
      "Session data API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not load session data (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session data endpoint did not return JSON.");
  }

  const payload = await response.json();
  return mapSessionDataPayload(payload);
}

function mapSessionDataPayload(payload) {
  return {
    session: payload.session,
    channels: Array.isArray(payload.channels)
      ? payload.channels.map(mapSessionDataChannel)
      : [],
    metrics: Array.isArray(payload.metrics) ? payload.metrics : [],
    events: Array.isArray(payload.events) ? payload.events.map(mapSessionDataEvent) : [],
    provenance: Array.isArray(payload.provenance) ? payload.provenance : [],
    races: Array.isArray(payload.races) ? payload.races.map(mapSessionRace) : [],
  };
}

export function getSessionEventCounts(sessionData) {
  return {
    tacks: countSessionDataEvents(sessionData, ["tack"]),
    gybes: countSessionDataEvents(sessionData, ["gybe", "jibe"]),
    capsizes: countSessionDataEvents(sessionData, ["capsize"]),
  };
}

export async function getSessionRaceData(sessionId, raceId) {
  let response;
  try {
    response = await fetch(getSessionRaceDataEndpoint(sessionId, raceId));
  } catch {
    throw new Error(
      "Race data API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not load race data (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Race data endpoint did not return JSON.");
  }

  const payload = await response.json();
  return mapSessionDataPayload(payload);
}

export async function updateSessionNotes(sessionId, notes) {
  let response;
  try {
    response = await fetch(getSessionNotesEndpoint(sessionId), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ notes }),
    });
  } catch {
    throw new Error(
      "Session notes API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not update session notes (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session notes endpoint did not return JSON.");
  }

  const payload = await response.json();
  return {
    sessionId: String(payload.session_id),
    notes: mapSessionNotes(payload.notes),
  };
}

function buildSessionRequestBody(sessionInput) {
  return {
    name: sessionInput.title,
    location: sessionInput.location,
    notes: sessionInput.notes,
  };
}

function mapSessionMutationResponse(payload) {
  return {
    id: String(payload.id),
    title: typeof payload.name === "string" ? payload.name : "",
    location: typeof payload.location === "string" ? payload.location : "",
    notes: mapSessionNotes(payload.notes),
  };
}

export async function updateSession(sessionId, sessionInput) {
  let response;
  try {
    response = await fetch(getSessionEndpoint(sessionId), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildSessionRequestBody(sessionInput)),
    });
  } catch {
    throw new Error(
      "Session API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not update session (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session endpoint did not return JSON.");
  }

  return mapSessionMutationResponse(await response.json());
}

export async function deleteSession(sessionId) {
  let response;
  try {
    response = await fetch(getSessionEndpoint(sessionId), {
      method: "DELETE",
    });
  } catch {
    throw new Error(
      "Session API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not delete session (${response.status}).`
    );
    throw new Error(errorText);
  }
}

export async function updateSessionManualWindDirection(sessionId, manualWindDirectionDeg) {
  let response;
  try {
    response = await fetch(getSessionManualWindDirectionEndpoint(sessionId), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        manual_wind_direction_deg:
          Number.isFinite(Number(manualWindDirectionDeg))
            ? Number(manualWindDirectionDeg)
            : null,
      }),
    });
  } catch {
    throw new Error(
      "Manual wind direction API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not update manual wind direction (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Manual wind direction endpoint did not return JSON.");
  }

  const payload = await response.json();
  return {
    sessionId: String(payload.session_id),
    manualWindDirectionDeg: toNullableNumber(payload.manual_wind_direction_deg),
  };
}

export async function triggerSessionVideo(
  sessionId,
  filePath,
  outputFolder = "",
  overlayLayout = {}
) {
  const normalizedOverlayLayout =
    overlayLayout && typeof overlayLayout === "object"
      ? Object.fromEntries(
          ["top", "bottom", "left", "right"].map((position) => [
            position,
            Array.isArray(overlayLayout[position])
              ? overlayLayout[position]
                  .map((channelName) =>
                    typeof channelName === "string" ? channelName.trim() : ""
                  )
                  .filter(Boolean)
              : [],
          ])
        )
      : {};
  const fallbackOverlayPosition =
    ["bottom", "top", "left", "right"].find(
      (position) => (normalizedOverlayLayout[position] ?? []).length > 0
    ) ?? "bottom";

  let response;
  try {
    response = await fetch(getSessionVideoEndpoint(sessionId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        file_path: typeof filePath === "string" ? filePath.trim() : "",
        output_folder: typeof outputFolder === "string" ? outputFolder.trim() : "",
        overlay_layout: normalizedOverlayLayout,
        overlay_position: fallbackOverlayPosition,
      }),
    });
  } catch {
    throw new Error(
      "Session video API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not trigger session video (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session video endpoint did not return JSON.");
  }

  const payload = await response.json();
  return {
    jobId: String(payload.job_id),
    status: payload.status,
    progressPercent: toNullableNumber(payload.progress_percent),
    message: typeof payload.message === "string" ? payload.message : "",
    outputFilePath:
      typeof payload.output_file_path === "string" ? payload.output_file_path : "",
    error: typeof payload.error === "string" ? payload.error : "",
  };
}

export async function getJobStatus(jobId) {
  let response;
  try {
    response = await fetch(getJobEndpoint(jobId));
  } catch {
    throw new Error(
      "Job status API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not load job status (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Job status endpoint did not return JSON.");
  }

  const payload = await response.json();
  return {
    jobId: String(payload.job_id),
    status: payload.status,
    progressPercent: toNullableNumber(payload.progress_percent),
    message: typeof payload.message === "string" ? payload.message : "",
    outputFilePath:
      typeof payload.output_file_path === "string" ? payload.output_file_path : "",
    error: typeof payload.error === "string" ? payload.error : "",
  };
}

export async function createSession({ sessionFile, metadata }) {
  if (!(sessionFile instanceof File)) {
    throw new Error("A session file is required.");
  }

  const formData = new FormData();
  formData.append("tcx_file", sessionFile, sessionFile.name || "session.tcx");
  formData.append(
    "metadata_json",
    new Blob([JSON.stringify(metadata)], { type: "application/json" }),
    "metadata.json"
  );

  const response = await fetch(getSessionsEndpoint(), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Session upload failed (${response.status}).`);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}

export async function exportSessionFiles(sessionId) {
  await downloadEndpointFile(
    getSessionExportEndpoint(sessionId, "csv"),
    `session-${sessionId}.csv`,
    "Session export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
  await downloadEndpointFile(
    getSessionExportEndpoint(sessionId, "txt"),
    `session-${sessionId}.txt`,
    "Session export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
}

export async function exportSessionRaceFiles(sessionId, raceId) {
  await downloadEndpointFile(
    getSessionRaceExportEndpoint(sessionId, raceId, "csv"),
    `race-${raceId}.csv`,
    "Race export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
  await downloadEndpointFile(
    getSessionRaceExportEndpoint(sessionId, raceId, "txt"),
    `race-${raceId}.txt`,
    "Race export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
}

export async function exportSessionRacesFiles(sessionId) {
  await downloadEndpointFile(
    getSessionRacesExportEndpoint(sessionId, "csv"),
    `session-${sessionId}-races.csv`,
    "Session races export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
  await downloadEndpointFile(
    getSessionRacesExportEndpoint(sessionId, "txt"),
    `session-${sessionId}-races.txt`,
    "Session races export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
}

export async function exportBoatFiles(boatId) {
  await downloadEndpointFile(
    getBoatExportEndpoint(boatId, "csv"),
    `boat-${boatId}.csv`,
    "Boat export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
  await downloadEndpointFile(
    getBoatExportEndpoint(boatId, "txt"),
    `boat-${boatId}.txt`,
    "Boat export API is unreachable. Start the backend API on http://127.0.0.1:8000."
  );
}

function buildBoatRequestBody(boatInput) {
  return {
    name: boatInput.name,
    class_name: boatInput.className,
    sailnumber: boatInput.sailNumber,
  };
}

function mapBoatMutationResponse(payload) {
  return {
    id: String(payload.id),
    name: typeof payload.name === "string" ? payload.name : "",
    className: typeof payload.class_name === "string" ? payload.class_name : "",
    sailNumber: typeof payload.sailnumber === "string" ? payload.sailnumber : "",
  };
}

export async function createBoat(boatInput) {
  let response;
  try {
    response = await fetch(getBoatsEndpoint(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildBoatRequestBody(boatInput)),
    });
  } catch {
    throw new Error(
      "Boat API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not create boat (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Boat endpoint did not return JSON.");
  }

  return mapBoatMutationResponse(await response.json());
}

export async function updateBoat(boatId, boatInput) {
  let response;
  try {
    response = await fetch(getBoatEndpoint(boatId), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildBoatRequestBody(boatInput)),
    });
  } catch {
    throw new Error(
      "Boat API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not update boat (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Boat endpoint did not return JSON.");
  }

  return mapBoatMutationResponse(await response.json());
}

export async function deleteBoat(boatId) {
  let response;
  try {
    response = await fetch(getBoatEndpoint(boatId), {
      method: "DELETE",
    });
  } catch {
    throw new Error(
      "Boat API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not delete boat (${response.status}).`
    );
    throw new Error(errorText);
  }
}

export async function createSessionRace(sessionId, raceInput) {
  let response;
  try {
    response = await fetch(getSessionRacesEndpoint(sessionId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name: raceInput.name,
        start_time: raceInput.startTime,
        finish_time: raceInput.endTime,
      }),
    });
  } catch {
    throw new Error(
      "Session races API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not create race (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session races endpoint did not return JSON.");
  }

  const payload = await response.json();
  return mapSessionRace(payload);
}

function buildRaceRequestBody(raceInput) {
  return {
    name: raceInput.name,
    start_time: raceInput.startTime,
    finish_time: raceInput.endTime,
  };
}

export async function updateSessionRace(sessionId, raceId, raceInput) {
  let response;
  try {
    response = await fetch(getSessionRaceEndpoint(sessionId, raceId), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildRaceRequestBody(raceInput)),
    });
  } catch {
    throw new Error(
      "Session races API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not update race (${response.status}).`
    );
    throw new Error(errorText);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error("Session race endpoint did not return JSON.");
  }

  return mapSessionRace(await response.json());
}

export async function deleteSessionRace(sessionId, raceId) {
  let response;
  try {
    response = await fetch(getSessionRaceEndpoint(sessionId, raceId), {
      method: "DELETE",
    });
  } catch {
    throw new Error(
      "Session races API is unreachable. Start the backend API on http://127.0.0.1:8000."
    );
  }

  if (!response.ok) {
    const errorText = await readErrorMessage(
      response,
      `Could not delete race (${response.status}).`
    );
    throw new Error(errorText);
  }
}
