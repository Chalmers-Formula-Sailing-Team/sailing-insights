import { useMemo, useState } from "react";
import { MapLibreTrackMapCanvas } from "./TrackReplayCard.jsx";

function getInitialFormValues(raceNumber) {
  return {
    name: `Race ${raceNumber}`,
  };
}

function formatElapsedDuration(startPoint, endPoint) {
  if (startPoint?.timestamp && endPoint?.timestamp) {
    const startTimeMs = new Date(startPoint.timestamp).getTime();
    const endTimeMs = new Date(endPoint.timestamp).getTime();
    if (!Number.isNaN(startTimeMs) && !Number.isNaN(endTimeMs) && endTimeMs > startTimeMs) {
      const totalSeconds = Math.round((endTimeMs - startTimeMs) / 1000);
      const hours = Math.floor(totalSeconds / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      if (hours === 0) {
        return `${minutes}:${String(seconds).padStart(2, "0")}`;
      }

      return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
  }

  if (startPoint?.elapsedMinutes !== undefined && endPoint?.elapsedMinutes !== undefined) {
    const elapsedMinutes = Math.max(endPoint.elapsedMinutes - startPoint.elapsedMinutes, 0);
    const hours = Math.floor(elapsedMinutes / 60);
    const minutes = elapsedMinutes % 60;
    if (hours === 0) {
      return `${minutes}m`;
    }

    if (minutes === 0) {
      return `${hours}h`;
    }

    return `${hours}h ${minutes}m`;
  }

  return "TBD";
}

function validateForm(name, hasReplay) {
  if (!name.trim()) {
    return "Race name is required.";
  }

  if (!hasReplay) {
    return "A replay track with at least two points is required.";
  }

  return "";
}

function normalizeRaceRange(startIndex, endIndex, maxIndex) {
  if (maxIndex <= 0) {
    return { startIndex: 0, endIndex: 0 };
  }

  const clampedStart = Math.max(0, Math.min(startIndex, maxIndex - 1));
  const clampedEnd = Math.max(1, Math.min(endIndex, maxIndex));

  if (clampedStart < clampedEnd) {
    return {
      startIndex: clampedStart,
      endIndex: clampedEnd,
    };
  }

  return {
    startIndex: Math.max(0, clampedEnd - 1),
    endIndex: clampedEnd,
  };
}

export function RaceWizardModal({ raceNumber, replay, onClose, onSubmit }) {
  const [formValues, setFormValues] = useState(() => getInitialFormValues(raceNumber));
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const maxIndex = Math.max(replay.trackPoints.length - 1, 0);
  const hasReplay = replay.trackPoints.length > 1;
  const [selectedRange, setSelectedRange] = useState(() =>
    normalizeRaceRange(0, maxIndex, maxIndex)
  );
  const { startIndex, endIndex } = selectedRange;

  const selectedStartPoint = replay.trackPoints[startIndex] ?? null;
  const selectedEndPoint = replay.trackPoints[endIndex] ?? null;
  const selectedDurationLabel = formatElapsedDuration(
    selectedStartPoint,
    selectedEndPoint
  );
  const sliderStyle = useMemo(
    () => ({
      "--range-start": `${maxIndex === 0 ? 0 : (startIndex / maxIndex) * 100}%`,
      "--range-end": `${maxIndex === 0 ? 100 : (endIndex / maxIndex) * 100}%`,
    }),
    [endIndex, maxIndex, startIndex]
  );

  async function handleSubmit(event) {
    event.preventDefault();
    const message = validateForm(formValues.name, hasReplay);
    if (message) {
      setErrorMessage(message);
      return;
    }

    setErrorMessage("");
    setIsSubmitting(true);

    try {
      await onSubmit({
        name: formValues.name.trim(),
        startTime: selectedStartPoint?.timestamp ?? null,
        endTime: selectedEndPoint?.timestamp ?? null,
        elapsedTime: selectedDurationLabel,
      });
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Unable to create race."
      );
      setIsSubmitting(false);
    }
  }

  return (
    <div className="wizard-overlay" role="presentation">
      <section
        className="wizard-modal wizard-modal--wide race-wizard-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="race-wizard-title"
      >
        <header className="wizard-header">
          <div>
            <p className="eyebrow">New race</p>
            <h3 id="race-wizard-title">Add race</h3>
          </div>
          <button type="button" className="ghost-button" onClick={onClose}>
            Cancel
          </button>
        </header>

        <form className="wizard-form" onSubmit={handleSubmit}>
          <div className="wizard-grid">
            <label className="wizard-field wizard-field--full">
              <span>Race name</span>
              <input
                type="text"
                value={formValues.name}
                onChange={(event) =>
                  setFormValues((currentValues) => ({
                    ...currentValues,
                    name: event.target.value,
                  }))
                }
                placeholder={`Race ${raceNumber}`}
              />
            </label>
          </div>

          <section className="race-range-picker" aria-label="Race time selection">
            <div className="track-map race-range-picker__map">
              <MapLibreTrackMapCanvas
                replay={replay}
                highlightRange={{ startIndex, endIndex }}
                className="race-range-picker__canvas"
                ariaLabel="Race range selection map"
                showActiveMarker={false}
                showBoundaryMarkers={false}
              />
              {!hasReplay && (
                <div className="track-map__empty">
                  <span className="material-icons" aria-hidden="true">route</span>
                  <p>No latitude/longitude track is available for this session yet.</p>
                </div>
              )}
            </div>

            <div className="race-range-slider" style={sliderStyle}>
              <div className="race-range-slider__track" aria-hidden="true" />
              <div className="race-range-slider__selection" aria-hidden="true" />
              <input
                className="race-range-slider__input"
                type="range"
                min="0"
                max={maxIndex}
                value={startIndex}
                disabled={!hasReplay}
                aria-label="Race start"
                onChange={(event) => {
                  const nextValue = Number(event.target.value);
                  setSelectedRange((currentRange) =>
                    normalizeRaceRange(nextValue, currentRange.endIndex, maxIndex)
                  );
                }}
              />
              <input
                className="race-range-slider__input"
                type="range"
                min="0"
                max={maxIndex}
                value={endIndex}
                disabled={!hasReplay}
                aria-label="Race finish"
                onChange={(event) => {
                  const nextValue = Number(event.target.value);
                  setSelectedRange((currentRange) =>
                    normalizeRaceRange(currentRange.startIndex, nextValue, maxIndex)
                  );
                }}
              />
              <div className="race-range-slider__labels" aria-hidden="true">
                <span>{replay.trackPoints[0]?.elapsedLabel ?? "Start"}</span>
                <span>{selectedDurationLabel}</span>
                <span>{replay.durationLabel ?? "Finish"}</span>
              </div>
            </div>
          </section>

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
              {isSubmitting ? "Creating..." : "Create race"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
