export function SessionCard({ session, onSelect, onEdit, onDelete }) {
  function handleActionClick(event, action) {
    event.stopPropagation();
    action();
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect();
    }
  }

  return (
    <article
      className="session-card session-card--interactive"
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
    >
      <div className="session-card__intro">
        <p className="session-card__date">{session.dateLabel}</p>
        <h3>{session.title}</h3>
        <p className="session-card__location">
          <span className="material-icons session-card__location-icon" aria-hidden="true">
            location_on
          </span>
          <span>{session.location}</span>
        </p>
      </div>

      <div className="session-card__stat">
        <span className="session-card__label">Duration</span>
        <strong>{session.durationLabel}</strong>
      </div>

      <div className="session-card__stat">
        <span className="session-card__label">Distance</span>
        <strong>{session.distanceLabel}</strong>
      </div>

      <div className="session-card__stat">
        <span className="session-card__label">Max speed</span>
        <strong>{session.maxSpeedLabel}</strong>
      </div>

      <div className="session-card__stat">
        <span className="session-card__label">Wind</span>
        <strong>{session.windLabel}</strong>
      </div>

      <div className="session-card__stat">
        <span className="session-card__label">Foiling avg</span>
        <strong>{session.foilingLabel}</strong>
      </div>

      <div className="session-card__actions">
        <button
          type="button"
          className="secondary-button"
          onClick={(event) => handleActionClick(event, onEdit)}
        >
          Edit
        </button>
        <button
          type="button"
          className="ghost-button ghost-button--danger"
          onClick={(event) => handleActionClick(event, onDelete)}
        >
          Delete
        </button>
      </div>
    </article>
  );
}
