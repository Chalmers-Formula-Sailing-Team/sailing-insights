import { BoatSessionsView } from "./BoatSessionsView.jsx";
import { FleetOverviewView } from "./FleetOverviewView.jsx";
import { SessionOverviewView } from "./SessionOverviewView.jsx";

export function DashboardView({
  status,
  screen,
  fleetSummary,
  boats,
  selectedBoatDetail,
  selectedSessionDetail,
  errorMessage,
  onBoatSelect,
  onBoatCreate,
  onBoatUpdate,
  onBoatDelete,
  onSessionSelect,
  onSessionUpdate,
  onSessionDelete,
  onSessionManualWindDirectionChange,
  onSessionNotesChange,
  onSessionVideoTrigger,
  onVideoJobStatusLoad,
  onSessionRaceCreate,
  onSessionRaceUpdate,
  onSessionRaceDelete,
  onSessionRaceDataLoad,
  onSessionRaceSelect,
  onBoatExport,
  onSessionExport,
  onSessionRacesExport,
  onRaceExport,
  onRaceScopeClear,
  onBackToFleet,
  onBackToBoat,
  onCreateSession,
}) {
  if (status === "loading") {
    return (
      <main className="dashboard-shell">
        <section className="dashboard-panel dashboard-panel--loading">
          <p className="eyebrow">Session dashboard</p>
          <h1>Loading sailing summary...</h1>
        </section>
      </main>
    );
  }

  if (status === "error") {
    return (
      <main className="dashboard-shell">
        <section className="dashboard-panel dashboard-panel--error">
          <p className="eyebrow">Session dashboard</p>
          <h1>Unable to load the sailing session.</h1>
          <p className="body-copy">{errorMessage}</p>
        </section>
      </main>
    );
  }

  if (screen === "boat-detail" && selectedBoatDetail) {
    return (
      <BoatSessionsView
        boatDetail={selectedBoatDetail}
        onSessionSelect={onSessionSelect}
        onBackToFleet={onBackToFleet}
        onCreateSession={onCreateSession}
        onSessionUpdate={onSessionUpdate}
        onSessionDelete={onSessionDelete}
        onBoatExport={onBoatExport}
      />
    );
  }

  if (screen === "session-detail" && selectedSessionDetail) {
    return (
      <SessionOverviewView
        sessionDetail={selectedSessionDetail}
        onSessionManualWindDirectionChange={onSessionManualWindDirectionChange}
        onSessionNotesChange={onSessionNotesChange}
        onSessionVideoTrigger={onSessionVideoTrigger}
        onVideoJobStatusLoad={onVideoJobStatusLoad}
        onSessionRaceCreate={onSessionRaceCreate}
        onSessionRaceUpdate={onSessionRaceUpdate}
        onSessionRaceDelete={onSessionRaceDelete}
        onSessionRaceDataLoad={onSessionRaceDataLoad}
        onSessionRaceSelect={onSessionRaceSelect}
        onSessionExport={onSessionExport}
        onSessionRacesExport={onSessionRacesExport}
        onRaceExport={onRaceExport}
        onRaceScopeClear={onRaceScopeClear}
        onBackToBoat={onBackToBoat}
      />
    );
  }

  return (
    <FleetOverviewView
      summary={fleetSummary}
      boats={boats}
      onBoatSelect={onBoatSelect}
      onBoatCreate={onBoatCreate}
      onBoatUpdate={onBoatUpdate}
      onBoatDelete={onBoatDelete}
    />
  );
}
