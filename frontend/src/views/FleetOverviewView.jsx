import { useState } from "react";
import { BoatCard } from "./components/BoatCard.jsx";
import { BoatFormModal } from "./components/BoatFormModal.jsx";
import { MetricCard } from "./components/MetricCard.jsx";

export function FleetOverviewView({
  summary,
  boats,
  onBoatSelect,
  onBoatCreate,
  onBoatUpdate,
  onBoatDelete,
}) {
  const [boatFormMode, setBoatFormMode] = useState(null);
  const [editingBoat, setEditingBoat] = useState(null);
  const [deletingBoat, setDeletingBoat] = useState(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  function openCreateForm() {
    setEditingBoat(null);
    setBoatFormMode("create");
  }

  function openEditForm(boat) {
    setEditingBoat(boat);
    setBoatFormMode("edit");
  }

  function closeBoatForm() {
    setBoatFormMode(null);
    setEditingBoat(null);
  }

  async function handleBoatFormSubmit(boatInput) {
    if (boatFormMode === "edit" && editingBoat) {
      await onBoatUpdate(editingBoat.id, boatInput);
    } else {
      await onBoatCreate(boatInput);
    }

    closeBoatForm();
  }

  async function handleDeleteConfirm() {
    if (!deletingBoat) {
      return;
    }

    setDeleteErrorMessage("");
    setIsDeleting(true);

    try {
      await onBoatDelete(deletingBoat.id);
      setDeletingBoat(null);
    } catch (error) {
      setDeleteErrorMessage(
        error instanceof Error ? error.message : "Unable to delete boat."
      );
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <section className="hero">
        <div className="hero__content">
          <p className="eyebrow">Sailing training dashboard</p>
          <h1>{summary.sailorName}</h1>
          <p className="hero__subtitle">
            A focused view of the current summer training block, with per-boat
            hours and a quick fleet summary.
          </p>
        </div>
        <div className="hero__meta">
          <span className="meta-chip">{summary.sessionWindow}</span>
          <span className="meta-chip">Fleet overview</span>
        </div>
      </section>

      <section className="summary-bar" aria-label="Session totals">
        <MetricCard
          label="Total hours trained"
          value={summary.totalHours}
          detail={`${summary.boatCount} boats tracked`}
        />
        <MetricCard
          label="Total distance sailed"
          value={summary.totalDistanceNm}
          detail="Logged across all boats"
        />
      </section>

      <section className="dashboard-panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Boat breakdown</p>
            <h2>Hours by boat</h2>
          </div>
          <div className="section-heading__actions">
            <button type="button" className="primary-button" onClick={openCreateForm}>
              Add boat
            </button>
          </div>
        </div>
        <div className="boat-grid">
          {boats.map((boat) => (
            <BoatCard
              key={boat.id}
              boat={boat}
              onSelect={() => onBoatSelect(boat.id)}
              onEdit={() => openEditForm(boat)}
              onDelete={() => {
                setDeleteErrorMessage("");
                setDeletingBoat(boat);
              }}
            />
          ))}
        </div>
      </section>

      {boatFormMode && (
        <BoatFormModal
          mode={boatFormMode}
          boat={editingBoat}
          onClose={closeBoatForm}
          onSubmit={handleBoatFormSubmit}
        />
      )}

      {deletingBoat && (
        <div className="wizard-overlay" role="presentation">
          <section
            className="wizard-modal boat-delete-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="boat-delete-title"
          >
            <header className="wizard-header">
              <div>
                <p className="eyebrow">Delete boat</p>
                <h3 id="boat-delete-title">{deletingBoat.name}</h3>
              </div>
              <button
                type="button"
                className="ghost-button"
                onClick={() => setDeletingBoat(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
            </header>

            <p className="body-copy boat-delete-modal__copy">
              This removes the boat, its sessions, and all session data.
            </p>

            {deleteErrorMessage && <p className="wizard-error">{deleteErrorMessage}</p>}

            <footer className="wizard-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setDeletingBoat(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
              >
                {isDeleting ? "Deleting..." : "Delete boat"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
