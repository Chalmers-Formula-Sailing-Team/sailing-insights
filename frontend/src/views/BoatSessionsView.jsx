import { useState } from "react";
import { MetricCard } from "./components/MetricCard.jsx";
import { SessionCard } from "./components/SessionCard.jsx";
import { SessionFormModal } from "./components/SessionFormModal.jsx";
import { SessionWizardModal } from "./components/SessionWizardModal.jsx";
import {
  CapsizeIcon,
  DistanceIcon,
  FoilingIcon,
  SessionsIcon,
  SpeedIcon,
  StopwatchIcon,
} from "./components/icons.jsx";

export function BoatSessionsView({
  boatDetail,
  onSessionSelect,
  onBackToFleet,
  onCreateSession,
  onSessionUpdate,
  onSessionDelete,
  onBoatExport,
}) {
  const { boat, summary, sessions } = boatDetail;
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [editingSession, setEditingSession] = useState(null);
  const [deletingSession, setDeletingSession] = useState(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  async function handleCreateSession(sessionInput) {
    await onCreateSession(boat.id, sessionInput);
    setIsWizardOpen(false);
  }

  async function handleUpdateSession(sessionInput) {
    if (!editingSession) {
      return;
    }

    await onSessionUpdate(editingSession.id, sessionInput);
    setEditingSession(null);
  }

  async function handleDeleteSession() {
    if (!deletingSession) {
      return;
    }

    setDeleteErrorMessage("");
    setIsDeleting(true);

    try {
      await onSessionDelete(deletingSession.id);
      setDeletingSession(null);
    } catch (error) {
      setDeleteErrorMessage(
        error instanceof Error ? error.message : "Unable to delete session."
      );
    } finally {
      setIsDeleting(false);
    }
  }

  async function handleExport() {
    setIsExporting(true);
    try {
      await onBoatExport(boat.id);
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <section className="hero">
        <div className="hero__content">
          <button type="button" className="back-button" onClick={onBackToFleet}>
            <span className="material-icons back-button__icon" aria-hidden="true">
              arrow_back
            </span>
            <span>Back to boats</span>
          </button>

          <h1>{boat.name}</h1>

        </div>
        <div className="hero__meta">
          <span className="meta-chip">{boat.className}</span>
          <span className="meta-chip">{sessions.length} sessions logged</span>
          <button
            type="button"
            className="secondary-button"
            onClick={handleExport}
            disabled={isExporting}
          >
            {isExporting ? "Exporting..." : "Export to CSV"}
          </button>
        </div>
      </section>

      <section
        className="summary-bar summary-bar--detail"
        aria-label="Boat session totals"
      >
        <MetricCard
          label="Total time"
          value={summary.totalTime}
          icon={<StopwatchIcon />}
          compact
        />
        <MetricCard
          label="Total distance"
          value={summary.totalDistance}
          icon={<DistanceIcon />}
          compact
        />
        <MetricCard
          label="Max speed"
          value={summary.maxSpeed}
          icon={<SpeedIcon />}
          compact
        />
        <MetricCard
          label="Sessions"
          value={summary.sessionsAmount}
          icon={<SessionsIcon />}
          compact
        />
        <MetricCard
          label="Average foiling"
          value={summary.averageFoiling}
          icon={<FoilingIcon />}
          compact
        />
        <MetricCard
          label="Capsizes"
          value={summary.capsizes}
          icon={<CapsizeIcon />}
          compact
        />
      </section>

      <section className="dashboard-panel">
        <div className="section-heading">
          <div>
            <h2>Sessions</h2>
          </div>
          <div className="section-heading__actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => setIsWizardOpen(true)}
            >
              Add session
            </button>
          </div>
        </div>

        <div className="session-list">
          {sessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              onSelect={() => onSessionSelect(session.id)}
              onEdit={() => setEditingSession(session)}
              onDelete={() => {
                setDeleteErrorMessage("");
                setDeletingSession(session);
              }}
            />
          ))}
        </div>
      </section>

      {isWizardOpen && (
        <SessionWizardModal
          boatName={boat.name}
          onClose={() => setIsWizardOpen(false)}
          onSubmit={handleCreateSession}
        />
      )}

      {editingSession && (
        <SessionFormModal
          session={editingSession}
          onClose={() => setEditingSession(null)}
          onSubmit={handleUpdateSession}
        />
      )}

      {deletingSession && (
        <div className="wizard-overlay" role="presentation">
          <section
            className="wizard-modal session-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-delete-title"
          >
            <header className="wizard-header">
              <div>
                <h3 id="session-delete-title">Delete {deletingSession.title}</h3>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => setDeletingSession(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
            </header>

            <p className="body-copy session-delete-modal__copy">
              This removes the session and all connected data.
            </p>

            {deleteErrorMessage && <p className="wizard-error">{deleteErrorMessage}</p>}

            <footer className="wizard-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setDeletingSession(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteSession}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting..." : "Delete session"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
