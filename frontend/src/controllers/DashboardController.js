import { useEffect, useState } from "react";
import { SailingSessionModel } from "../models/SailingSessionModel.js";
import {
  createBoat,
  createSessionRace,
  createSession,
  deleteBoat,
  deleteSession,
  deleteSessionRace,
  exportBoatFiles,
  exportSessionFiles,
  exportSessionRacesFiles,
  exportSessionRaceFiles,
  getJobStatus,
  getSailingSession,
  getSessionData,
  getSessionEventCounts,
  getSessionRaceData,
  triggerSessionVideo,
  updateBoat,
  updateSession,
  updateSessionRace,
  updateSessionManualWindDirection,
  updateSessionNotes,
} from "../services/sessionService.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toNumberOr(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function normalizeIsoTimestamp(value) {
  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return null;
  }

  return parsedDate.toISOString().replace(".000Z", "Z");
}

function getFallbackTimeRange(dateInput) {
  const dateMatch =
    typeof dateInput === "string" ? dateInput.match(/^(\d{4})-(\d{2})-(\d{2})$/) : null;
  const safeDate = dateMatch ? dateMatch[0] : new Date().toISOString().slice(0, 10);

  return {
    start_ts: `${safeDate}T00:00:00Z`,
    end_ts: `${safeDate}T02:00:00Z`,
  };
}

function isTcxFile(file) {
  if (!(file instanceof File)) {
    return false;
  }

  const normalizedName = file.name.toLowerCase();
  return (
    normalizedName.endsWith(".tcx")
    || file.type === "application/xml"
    || file.type === "text/xml"
  );
}

async function getSessionTimeRangeFromSessionFile(sessionFile, dateInput) {
  const fallbackTimeRange = getFallbackTimeRange(dateInput);
  if (!(sessionFile instanceof File)) {
    return fallbackTimeRange;
  }

  if (!isTcxFile(sessionFile)) {
    return null;
  }

  try {
    const tcxText = await sessionFile.text();
    const timeMatches = [...tcxText.matchAll(/<Time>([^<]+)<\/Time>/g)];
    if (timeMatches.length === 0) {
      return fallbackTimeRange;
    }

    const startTs = normalizeIsoTimestamp(timeMatches[0][1]) ?? fallbackTimeRange.start_ts;
    const endTs =
      normalizeIsoTimestamp(timeMatches[timeMatches.length - 1][1]) ??
      fallbackTimeRange.end_ts;

    return {
      start_ts: startTs,
      end_ts: endTs,
    };
  } catch {
    return fallbackTimeRange;
  }
}

function normalizeWindDirectionDegreesString(windDirectionInput) {
  if (windDirectionInput === null || windDirectionInput === undefined) {
    return "0";
  }

  const numericDirection = Number(windDirectionInput);
  if (!Number.isFinite(numericDirection)) {
    return "0";
  }

  const clampedDirection = ((Math.round(numericDirection) % 360) + 360) % 360;
  return String(clampedDirection);
}

function normalizeNonNegativeDecimalString(value, fallback = 0) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return String(fallback);
  }

  return String(Math.max(numericValue, 0));
}

function normalizeOptionalDecimalString(value) {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }

  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return undefined;
  }

  return String(numericValue);
}

function buildUploadMetadata({ boatName, sessionInput, timeRange }) {
  const sessionName =
    typeof sessionInput.title === "string" && sessionInput.title.trim()
      ? sessionInput.title.trim()
      : "default session";
  const windSpeedInput = sessionInput.windStrengthKts ?? sessionInput.windSpeedKts;
  const windSpeed = String(clamp(Math.round(toNumberOr(windSpeedInput, 0)), 0, 200));
  const windGustInput = sessionInput.windGustKts;
  const windGust = String(clamp(Math.round(toNumberOr(windGustInput, 0)), 0, 200));
  const notes =
    typeof sessionInput.notes === "string" && sessionInput.notes.trim()
      ? sessionInput.notes.trim()
      : undefined;
  const location =
    typeof sessionInput.location === "string" && sessionInput.location.trim()
      ? sessionInput.location.trim()
      : undefined;

  return {
    sessionName,
    boat: boatName,
    location,
    windDirection: normalizeWindDirectionDegreesString(sessionInput.windDirection),
    windSpeed,
    windGust,
    waveHeightM: normalizeNonNegativeDecimalString(sessionInput.waveHeightM, 0),
    rideHeightOffsetCm: normalizeOptionalDecimalString(sessionInput.rideHeightOffsetCm),
    notes,
    start_ts: timeRange?.start_ts,
    end_ts: timeRange?.end_ts,
  };
}

function getBoatSessionCount(sessionData, boatId) {
  const targetBoat = sessionData.boats.find((boat) => boat.id === boatId);
  return targetBoat ? targetBoat.sessions.length : 0;
}

function delay(milliseconds) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}

async function refreshDashboardFromDbAfterUpload(boatId, previousSessionCount) {
  const expectedSessionCount = previousSessionCount + 1;
  let latestSessionData = await getSailingSession();

  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (getBoatSessionCount(latestSessionData, boatId) >= expectedSessionCount) {
      return latestSessionData;
    }

    await delay(600);
    latestSessionData = await getSailingSession();
  }

  return latestSessionData;
}

function updateNotesInSessionData(data, sessionId, notes) {
  if (!data) {
    return data;
  }

  return {
    ...data,
    boats: data.boats.map((boat) => ({
      ...boat,
      sessions: boat.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              notes,
            }
          : session
      ),
    })),
  };
}

function updateManualWindDirectionInSessionData(data, sessionId, manualWindDirectionDeg) {
  if (!data) {
    return data;
  }

  const normalizedManualWindDirectionDeg =
    Number.isFinite(Number(manualWindDirectionDeg))
      ? ((Math.round(Number(manualWindDirectionDeg)) % 360) + 360) % 360
      : null;

  return {
    ...data,
    boats: data.boats.map((boat) => ({
      ...boat,
      sessions: boat.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              manualWindDirectionDeg: normalizedManualWindDirectionDeg,
            }
          : session
      ),
    })),
  };
}

function updateSessionEventCountsInSessionData(data, sessionId, sessionData) {
  if (!data || !sessionData) {
    return data;
  }

  const { tacks, gybes, capsizes } = getSessionEventCounts(sessionData);

  return {
    ...data,
    boats: data.boats.map((boat) => ({
      ...boat,
      sessions: boat.sessions.map((session) =>
        session.id === sessionId
          ? {
              ...session,
              tacks,
              gybes,
              capsizes,
            }
          : session
      ),
    })),
  };
}

function appendRaceToSessionData(sessionDataById, sessionId, race) {
  const existingSessionData = sessionDataById[sessionId];
  if (!existingSessionData) {
    return sessionDataById;
  }

  return {
    ...sessionDataById,
    [sessionId]: {
      ...existingSessionData,
      races: [...(existingSessionData.races ?? []), race],
    },
  };
}

function getRaceDataKey(sessionId, raceId) {
  return `${sessionId}:${raceId}`;
}

export function useDashboardController() {
  const [state, setState] = useState({
    status: "loading",
    data: null,
    selectedBoatId: null,
    selectedSessionId: null,
    selectedRaceId: null,
    sessionDataById: {},
    raceDataById: {},
    errorMessage: "",
  });

  useEffect(() => {
    let active = true;

    async function loadSession() {
      try {
        const sessionData = await getSailingSession();

        if (!active) {
          return;
        }

        setState({
          status: "ready",
          data: sessionData,
          selectedBoatId: null,
          selectedSessionId: null,
          selectedRaceId: null,
          sessionDataById: {},
          raceDataById: {},
          errorMessage: "",
        });
      } catch (error) {
        if (!active) {
          return;
        }

        setState({
          status: "error",
          data: null,
          selectedBoatId: null,
          selectedSessionId: null,
          selectedRaceId: null,
          sessionDataById: {},
          raceDataById: {},
          errorMessage:
            error instanceof Error
              ? error.message
              : "The sailing session could not be loaded.",
        });
      }
    }

    loadSession();

    return () => {
      active = false;
    };
  }, []);

  if (state.status !== "ready" || !state.data) {
    return {
      status: state.status,
      screen: "fleet",
      fleetSummary: null,
      boats: [],
      selectedBoatDetail: null,
      selectedSessionDetail: null,
      errorMessage: state.errorMessage,
      onBoatSelect: () => {},
      onBoatCreate: async () => {},
      onBoatUpdate: async () => {},
      onBoatDelete: async () => {},
      onSessionSelect: () => {},
      onSessionUpdate: async () => {},
      onSessionDelete: async () => {},
      onSessionNotesChange: async () => {},
      onSessionManualWindDirectionChange: async () => {},
      onSessionVideoTrigger: async () => {},
      onVideoJobStatusLoad: async () => {},
      onSessionRaceCreate: async () => {},
      onSessionRaceUpdate: async () => {},
      onSessionRaceDelete: async () => {},
      onSessionRaceDataLoad: async () => {},
      onSessionRaceSelect: async () => {},
      onBoatExport: async () => {},
      onSessionExport: async () => {},
      onSessionRacesExport: async () => {},
      onRaceExport: async () => {},
      onRaceScopeClear: () => {},
      onBackToFleet: () => {},
      onBackToBoat: () => {},
      onCreateSession: () => {},
    };
  }

  const sessionModel = new SailingSessionModel(state.data);
  const fleetSummary = sessionModel.getFleetSummary();
  const boats = sessionModel.getBoats();
  const selectedBoatDetail = state.selectedBoatId
    ? sessionModel.getBoatDetail(state.selectedBoatId)
    : null;
  const selectedSessionDetail =
    state.selectedBoatId && state.selectedSessionId
      ? sessionModel.getSessionDetail(state.selectedBoatId, state.selectedSessionId)
      : null;
  const selectedSessionDetailWithData =
    selectedSessionDetail && state.selectedSessionId
      ? {
          ...selectedSessionDetail,
          selectedRaceId: state.selectedRaceId,
          raceData:
            state.selectedSessionId && state.selectedRaceId
              ? state.raceDataById[
                  getRaceDataKey(state.selectedSessionId, state.selectedRaceId)
                ] ?? null
              : null,
          raceDataByRaceId: state.selectedSessionId
            ? Object.fromEntries(
                Object.entries(state.raceDataById)
                  .filter(([key]) => key.startsWith(`${state.selectedSessionId}:`))
                  .map(([key, value]) => [key.slice(state.selectedSessionId.length + 1), value])
              )
            : {},
          session: {
            ...selectedSessionDetail.session,
            data: state.sessionDataById[state.selectedSessionId] ?? null,
          },
        }
      : null;

  return {
    status: state.status,
    screen: selectedSessionDetailWithData
      ? "session-detail"
      : selectedBoatDetail
        ? "boat-detail"
        : "fleet",
    fleetSummary,
    boats,
    selectedBoatDetail,
    selectedSessionDetail: selectedSessionDetailWithData,
    errorMessage: state.errorMessage,
    onBoatSelect: (boatId) => {
      setState((currentState) => ({
        ...currentState,
        selectedBoatId: boatId,
        selectedSessionId: null,
        selectedRaceId: null,
      }));
    },
    onBoatCreate: async (boatInput) => {
      const createdBoat = await createBoat(boatInput);
      const refreshedData = await getSailingSession();

      setState((currentState) => ({
        ...currentState,
        status: "ready",
        data: refreshedData,
        selectedBoatId: null,
        selectedSessionId: null,
        selectedRaceId: null,
        sessionDataById: {},
        raceDataById: {},
        errorMessage: "",
      }));

      return createdBoat;
    },
    onBoatUpdate: async (boatId, boatInput) => {
      const updatedBoat = await updateBoat(boatId, boatInput);
      const refreshedData = await getSailingSession();

      setState((currentState) => ({
        ...currentState,
        status: "ready",
        data: refreshedData,
        selectedBoatId:
          currentState.selectedBoatId === boatId ? updatedBoat.id : currentState.selectedBoatId,
        errorMessage: "",
      }));

      return updatedBoat;
    },
    onBoatDelete: async (boatId) => {
      await deleteBoat(boatId);
      const refreshedData = await getSailingSession();

      setState((currentState) => {
        const isSelectedBoat = currentState.selectedBoatId === boatId;

        return {
          ...currentState,
          status: "ready",
          data: refreshedData,
          selectedBoatId: isSelectedBoat ? null : currentState.selectedBoatId,
          selectedSessionId: isSelectedBoat ? null : currentState.selectedSessionId,
          selectedRaceId: isSelectedBoat ? null : currentState.selectedRaceId,
          sessionDataById: isSelectedBoat ? {} : currentState.sessionDataById,
          raceDataById: isSelectedBoat ? {} : currentState.raceDataById,
          errorMessage: "",
        };
      });
    },
    onSessionSelect: async (sessionId) => {
      try {
        const cachedSessionData = state.sessionDataById[sessionId];
        const sessionData = cachedSessionData ?? await getSessionData(sessionId);

        setState((currentState) => ({
          ...currentState,
          selectedSessionId: sessionId,
          selectedRaceId: null,
          sessionDataById: {
            ...currentState.sessionDataById,
            [sessionId]: sessionData,
          },
          errorMessage: "",
        }));
      } catch (error) {
        setState((currentState) => ({
          ...currentState,
          status: "error",
          errorMessage:
            error instanceof Error
              ? error.message
              : "The session data could not be loaded.",
        }));
      }
    },
    onSessionUpdate: async (sessionId, sessionInput) => {
      const updatedSession = await updateSession(sessionId, sessionInput);
      const refreshedData = await getSailingSession();

      setState((currentState) => ({
        ...currentState,
        status: "ready",
        data: refreshedData,
        sessionDataById: currentState.sessionDataById[sessionId]
          ? {
              ...currentState.sessionDataById,
              [sessionId]: {
                ...currentState.sessionDataById[sessionId],
                session: {
                  ...currentState.sessionDataById[sessionId].session,
                  name: updatedSession.title,
                  location: updatedSession.location,
                  notes: updatedSession.notes,
                },
              },
            }
          : currentState.sessionDataById,
        errorMessage: "",
      }));

      return updatedSession;
    },
    onSessionDelete: async (sessionId) => {
      await deleteSession(sessionId);
      const refreshedData = await getSailingSession();

      setState((currentState) => {
        const nextSessionDataById = { ...currentState.sessionDataById };
        delete nextSessionDataById[sessionId];

        const nextRaceDataById = Object.fromEntries(
          Object.entries(currentState.raceDataById).filter(
            ([key]) => !key.startsWith(`${sessionId}:`)
          )
        );

        return {
          ...currentState,
          status: "ready",
          data: refreshedData,
          selectedSessionId:
            currentState.selectedSessionId === sessionId ? null : currentState.selectedSessionId,
          selectedRaceId:
            currentState.selectedSessionId === sessionId ? null : currentState.selectedRaceId,
          sessionDataById: nextSessionDataById,
          raceDataById: nextRaceDataById,
          errorMessage: "",
        };
      });
    },
    onSessionNotesChange: async (sessionId, notes) => {
      const updatedSession = await updateSessionNotes(sessionId, notes);

      setState((currentState) => {
        const existingSessionData = currentState.sessionDataById[sessionId];

        return {
          ...currentState,
          data: updateNotesInSessionData(
            currentState.data,
            sessionId,
            updatedSession.notes
          ),
          sessionDataById: existingSessionData
            ? {
                ...currentState.sessionDataById,
                [sessionId]: {
                  ...existingSessionData,
                  session: {
                    ...existingSessionData.session,
                    notes: updatedSession.notes,
                  },
                },
              }
            : currentState.sessionDataById,
          errorMessage: "",
        };
      });

      return updatedSession;
    },
    onSessionManualWindDirectionChange: async (sessionId, manualWindDirectionDeg) => {
      const updatedSession = await updateSessionManualWindDirection(
        sessionId,
        manualWindDirectionDeg
      );
      const shouldRefreshSessionData =
        state.selectedSessionId === sessionId || Boolean(state.sessionDataById[sessionId]);
      const refreshedSessionData = shouldRefreshSessionData
        ? await getSessionData(sessionId)
        : null;

      setState((currentState) => ({
        ...currentState,
        data: updateSessionEventCountsInSessionData(
          updateManualWindDirectionInSessionData(
            currentState.data,
            sessionId,
            updatedSession.manualWindDirectionDeg
          ),
          sessionId,
          refreshedSessionData
        ),
        sessionDataById: refreshedSessionData
          ? {
              ...currentState.sessionDataById,
              [sessionId]: refreshedSessionData,
            }
          : currentState.sessionDataById,
        errorMessage: "",
      }));

      return updatedSession;
    },
    onSessionVideoTrigger: async (sessionId, filePath, outputFolder, overlayLayout) => {
      const job = await triggerSessionVideo(
        sessionId,
        filePath,
        outputFolder,
        overlayLayout
      );
      return job;
    },
    onVideoJobStatusLoad: async (jobId) => {
      return getJobStatus(jobId);
    },
    onSessionRaceCreate: async (sessionId, raceInput) => {
      const createdRace = await createSessionRace(sessionId, raceInput);

      setState((currentState) => ({
        ...currentState,
        sessionDataById: appendRaceToSessionData(
          currentState.sessionDataById,
          sessionId,
          createdRace
        ),
        errorMessage: "",
      }));

      return createdRace;
    },
    onSessionRaceUpdate: async (sessionId, raceId, raceInput) => {
      const updatedRace = await updateSessionRace(sessionId, raceId, raceInput);

      setState((currentState) => {
        const existingSessionData = currentState.sessionDataById[sessionId];
        const raceDataKey = getRaceDataKey(sessionId, raceId);
        const nextRaceDataById = { ...currentState.raceDataById };
        delete nextRaceDataById[raceDataKey];

        return {
          ...currentState,
          sessionDataById: existingSessionData
            ? {
                ...currentState.sessionDataById,
                [sessionId]: {
                  ...existingSessionData,
                  races: (existingSessionData.races ?? []).map((race) =>
                    race.id === raceId ? updatedRace : race
                  ),
                },
            }
            : currentState.sessionDataById,
          raceDataById: nextRaceDataById,
          errorMessage: "",
        };
      });

      return updatedRace;
    },
    onSessionRaceDelete: async (sessionId, raceId) => {
      await deleteSessionRace(sessionId, raceId);

      setState((currentState) => {
        const existingSessionData = currentState.sessionDataById[sessionId];
        const raceDataKey = getRaceDataKey(sessionId, raceId);
        const nextRaceDataById = { ...currentState.raceDataById };
        delete nextRaceDataById[raceDataKey];

        return {
          ...currentState,
          selectedRaceId: currentState.selectedRaceId === raceId ? null : currentState.selectedRaceId,
          sessionDataById: existingSessionData
            ? {
                ...currentState.sessionDataById,
                [sessionId]: {
                  ...existingSessionData,
                  races: (existingSessionData.races ?? []).filter((race) => race.id !== raceId),
                },
              }
            : currentState.sessionDataById,
          raceDataById: nextRaceDataById,
          errorMessage: "",
        };
      });
    },
    onSessionRaceDataLoad: async (sessionId, raceId) => {
      const raceDataKey = getRaceDataKey(sessionId, raceId);
      const cachedRaceData = state.raceDataById[raceDataKey];
      if (cachedRaceData) {
        return cachedRaceData;
      }

      const raceData = await getSessionRaceData(sessionId, raceId);

      setState((currentState) => ({
        ...currentState,
        raceDataById: {
          ...currentState.raceDataById,
          [raceDataKey]: raceData,
        },
        errorMessage: "",
      }));

      return raceData;
    },
    onSessionRaceSelect: async (sessionId, raceId) => {
      try {
        const raceDataKey = getRaceDataKey(sessionId, raceId);
        const cachedRaceData = state.raceDataById[raceDataKey];
        const raceData =
          cachedRaceData ?? await getSessionRaceData(sessionId, raceId);

        setState((currentState) => ({
          ...currentState,
          selectedRaceId: raceId,
          raceDataById: {
            ...currentState.raceDataById,
            [raceDataKey]: raceData,
          },
          errorMessage: "",
        }));
      } catch (error) {
        setState((currentState) => ({
          ...currentState,
          status: "error",
          errorMessage:
            error instanceof Error
              ? error.message
              : "The race data could not be loaded.",
        }));
      }
    },
    onBoatExport: async (boatId) => {
      await exportBoatFiles(boatId);
    },
    onSessionExport: async (sessionId) => {
      await exportSessionFiles(sessionId);
    },
    onSessionRacesExport: async (sessionId) => {
      await exportSessionRacesFiles(sessionId);
    },
    onRaceExport: async (sessionId, raceId) => {
      await exportSessionRaceFiles(sessionId, raceId);
    },
    onRaceScopeClear: () => {
      setState((currentState) => ({
        ...currentState,
        selectedRaceId: null,
      }));
    },
    onBackToFleet: () => {
      setState((currentState) => ({
        ...currentState,
        selectedBoatId: null,
        selectedSessionId: null,
        selectedRaceId: null,
      }));
    },
    onBackToBoat: () => {
      setState((currentState) => ({
        ...currentState,
        selectedSessionId: null,
        selectedRaceId: null,
      }));
    },
    onCreateSession: async (boatId, sessionInput) => {
      const { sessionFile, ...manualData } = sessionInput;
      const boatName = state.data.boats.find((boat) => boat.id === boatId)?.name ?? boatId;
      const previousSessionCount = getBoatSessionCount(state.data, boatId);
      const timeRange = await getSessionTimeRangeFromSessionFile(
        sessionFile,
        manualData.date
      );
      const metadata = buildUploadMetadata({
        boatName,
        sessionInput: manualData,
        timeRange,
      });

      await createSession({
        sessionFile,
        metadata,
      });

      const refreshedData = await refreshDashboardFromDbAfterUpload(
        boatId,
        previousSessionCount
      );

      setState((currentState) => ({
        ...currentState,
        status: "ready",
        data: refreshedData,
        selectedBoatId: boatId,
        selectedSessionId: null,
        selectedRaceId: null,
        sessionDataById: {},
        raceDataById: {},
        errorMessage: "",
      }));
    },
  };
}
