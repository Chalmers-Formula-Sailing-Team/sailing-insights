import { useEffect, useState } from "react";
import { buildTrackPath, projectTrackPoints, sampleTrackPoints } from "../../utils/trackMap.js";

const PREVIEW_POINT_LIMIT = 6000;

function parseTrackPointsFromTcx(tcxText) {
  const parsedXml = new DOMParser().parseFromString(tcxText, "application/xml");
  if (parsedXml.querySelector("parsererror")) {
    return { pointCount: 0, points: [] };
  }

  const trackpoints = Array.from(parsedXml.getElementsByTagName("Trackpoint"));
  const parsedPoints = [];

  for (const trackpoint of trackpoints) {
    const latitudeText = trackpoint.getElementsByTagName("LatitudeDegrees")[0]?.textContent;
    const longitudeText = trackpoint.getElementsByTagName("LongitudeDegrees")[0]?.textContent;
    const latitude = Number(latitudeText);
    const longitude = Number(longitudeText);

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      continue;
    }

    parsedPoints.push({ latitude, longitude });
  }

  return {
    pointCount: parsedPoints.length,
    points: sampleTrackPoints(parsedPoints, PREVIEW_POINT_LIMIT),
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

function getInitialFormValues() {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  const year = String(today.getFullYear());

  return {
    title: "",
    date: `${year}-${month}-${day}`,
    location: "Langedrag",
    windSpeedKts: "14",
    windGustKts: "18",
    windDirection: "225",
    waveHeightM: "0.1",
    rideHeightOffsetCm: "-24",
    notes: "",
  };
}

function parseFormValues(values) {
  const rideHeightOffsetCm = values.rideHeightOffsetCm.trim();

  return {
    title: values.title.trim(),
    date: values.date,
    location: values.location.trim(),
    windDirection: values.windDirection.trim(),
    windSpeedKts: Number(values.windSpeedKts),
    windGustKts: Number(values.windGustKts),
    waveHeightM: Number(values.waveHeightM),
    rideHeightOffsetCm:
      rideHeightOffsetCm === "" ? null : Number(rideHeightOffsetCm),
    notes: values.notes.trim(),
  };
}

function validateForm(values) {
  if (!values.title.trim()) {
    return "Session name is required.";
  }

  if (!values.location.trim()) {
    return "Location is required.";
  }

  if (!values.windDirection.trim()) {
    return "Wind direction is required.";
  }

  const windDirection = Number(values.windDirection);
  if (!Number.isInteger(windDirection) || windDirection < 0 || windDirection > 359) {
    return "Wind direction must be an integer between 0 and 359.";
  }

  if (!Number.isFinite(Number(values.windSpeedKts)) || Number(values.windSpeedKts) < 0) {
    return "Wind speed must be 0 or higher.";
  }

  if (!Number.isFinite(Number(values.windGustKts)) || Number(values.windGustKts) < 0) {
    return "Wind gusts must be 0 or higher.";
  }

  if (!Number.isFinite(Number(values.waveHeightM)) || Number(values.waveHeightM) < 0) {
    return "Wave height must be 0 or higher.";
  }

  if (
    values.rideHeightOffsetCm.trim() !== ""
    && !Number.isFinite(Number(values.rideHeightOffsetCm))
  ) {
    return "Ride hight offset must be a valid number.";
  }

  return "";
}

export function SessionWizardModal({ boatName, onClose, onSubmit }) {
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sessionFile, setSessionFile] = useState(null);
  const [formValues, setFormValues] = useState(() => getInitialFormValues());
  const [trackPreview, setTrackPreview] = useState({
    status: "idle",
    pointCount: 0,
    points: [],
  });

  useEffect(() => {
    let isCanceled = false;

    async function loadTrackPreview() {
      if (!(sessionFile instanceof File)) {
        setTrackPreview({
          status: "idle",
          pointCount: 0,
          points: [],
        });
        return;
      }

      if (!isTcxFile(sessionFile)) {
        setTrackPreview({
          status: "unavailable",
          pointCount: 0,
          points: [],
        });
        return;
      }

      setTrackPreview({
        status: "loading",
        pointCount: 0,
        points: [],
      });

      try {
        const tcxText = await sessionFile.text();
        if (isCanceled) {
          return;
        }

        const parsedTrack = parseTrackPointsFromTcx(tcxText);

        if (parsedTrack.pointCount < 2) {
          setTrackPreview({
            status: "empty",
            pointCount: parsedTrack.pointCount,
            points: [],
          });
          return;
        }

        setTrackPreview({
          status: "ready",
          pointCount: parsedTrack.pointCount,
          points: projectTrackPoints(parsedTrack.points),
        });
      } catch {
        if (isCanceled) {
          return;
        }

        setTrackPreview({
          status: "error",
          pointCount: 0,
          points: [],
        });
      }
    }

    loadTrackPreview();

    return () => {
      isCanceled = true;
    };
  }, [sessionFile]);

  const trackPath = buildTrackPath(trackPreview.points);
  const startPoint = trackPreview.points[0];
  const endPoint = trackPreview.points[trackPreview.points.length - 1];

  function updateField(fieldName, value) {
    setFormValues((currentValues) => ({
      ...currentValues,
      [fieldName]: value,
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validateForm(formValues);

    if (message) {
      setErrorMessage(message);
      return;
    }

    if (!(sessionFile instanceof File)) {
      setErrorMessage("A session file is required.");
      return;
    }

    setErrorMessage("");
    setIsSubmitting(true);

    try {
      await onSubmit({
        ...parseFormValues(formValues),
        sessionFile,
      });
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to create session."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="wizard-overlay" role="presentation">
      <section
        className="wizard-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-wizard-title"
      >
        <header className="wizard-header">
          <div>
            <p className="eyebrow">New session</p>
            <h3 id="session-wizard-title">Add a session for {boatName}</h3>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
        </header>

        <form className="wizard-form" onSubmit={handleSubmit}>
          <div className="wizard-grid">
            <label className="wizard-field wizard-field--full">
              <span>Session name</span>
              <input
                type="text"
                value={formValues.title}
                onChange={(event) => updateField("title", event.target.value)}
                placeholder="Race simulation"
              />
            </label>

            <label className="wizard-field">
              <span>Wind direction (deg)</span>
              <input
                type="number"
                min="0"
                max="359"
                step="1"
                value={formValues.windDirection}
                onChange={(event) => updateField("windDirection", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Wind speed (kn)</span>
              <input
                type="number"
                min="0"
                step="1"
                value={formValues.windSpeedKts}
                onChange={(event) => updateField("windSpeedKts", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Wind gusts (kn)</span>
              <input
                type="number"
                min="0"
                step="1"
                value={formValues.windGustKts}
                onChange={(event) => updateField("windGustKts", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Wave height (m)</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={formValues.waveHeightM}
                onChange={(event) => updateField("waveHeightM", event.target.value)}
              />
            </label>

            <label className="wizard-field">
              <span>Ride hight offset (cm)</span>
              <input
                type="number"
                step="1"
                value={formValues.rideHeightOffsetCm}
                onChange={(event) => updateField("rideHeightOffsetCm", event.target.value)}
              />
            </label>

            <label className="wizard-field wizard-field--full">
              <span>Location</span>
              <input
                type="text"
                value={formValues.location}
                onChange={(event) => updateField("location", event.target.value)}
                placeholder="Askrikefjarden"
              />
            </label>

            <label className="wizard-field wizard-field--full">
              <span>Notes</span>
              <textarea
                rows="5"
                value={formValues.notes}
                onChange={(event) => updateField("notes", event.target.value)}
                placeholder="Crew setup, sea state, drills, what felt fast, what to review..."
              />
            </label>

            <label className="wizard-field wizard-field--full">
              <span>Session file (.tcx, .fit, or .csv)</span>
              <input
                type="file"
                accept=".tcx,.fit,.csv,application/xml,text/xml,text/csv"
                onChange={(event) => {
                  setErrorMessage("");
                  setSessionFile(event.target.files?.[0] || null);
                }}
              />
              {sessionFile && (
                <div className="wizard-track-preview" aria-live="polite">
                  <div className="wizard-track-preview__meta">
                    <span className="wizard-track-preview__title">
                      <span className="material-icons" aria-hidden="true">route</span>
                      <span>Track preview</span>
                    </span>
                    {trackPreview.status === "ready" && (
                      <span>{trackPreview.pointCount} points</span>
                    )}
                  </div>

                  {trackPreview.status === "loading" && (
                    <p className="wizard-track-preview__status">Reading {sessionFile.name}...</p>
                  )}

                  {trackPreview.status === "empty" && (
                    <p className="wizard-track-preview__status">
                      No track points were found in this file.
                    </p>
                  )}

                  {trackPreview.status === "unavailable" && (
                    <p className="wizard-track-preview__status">
                      Track preview is currently available for TCX files only.
                    </p>
                  )}

                  {trackPreview.status === "error" && (
                    <p className="wizard-track-preview__status">
                      This file could not be parsed as a TCX track preview.
                    </p>
                  )}

                  {trackPreview.status === "ready" && startPoint && endPoint && (
                    <div className="wizard-track-preview__map">
                      <svg
                        viewBox="0 0 100 100"
                        className="wizard-track-preview__svg"
                        aria-label="Selected track preview"
                      >
                        <path d={trackPath} className="wizard-track-preview__path" />
                        <circle
                          cx={startPoint.x}
                          cy={startPoint.y}
                          r="2.2"
                          className="wizard-track-preview__marker wizard-track-preview__marker--start"
                        />
                        <circle
                          cx={endPoint.x}
                          cy={endPoint.y}
                          r="2.6"
                          className="wizard-track-preview__marker wizard-track-preview__marker--end"
                        />
                      </svg>
                    </div>
                  )}
                </div>
              )}
            </label>
          </div>

          {errorMessage && <p className="wizard-error">{errorMessage}</p>}

          <footer className="wizard-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Creating..." : "Create session"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
