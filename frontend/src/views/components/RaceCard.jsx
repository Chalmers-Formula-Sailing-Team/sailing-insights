export function RaceCard({
  race,
  isActive = false,
  isLoading = false,
  onSelect,
  onEdit,
  onDelete,
}) {
  function handleActionClick(event, action) {
    event.stopPropagation();
    action();
  }

  function handleKeyDown(event) {
    if ((event.key === "Enter" || event.key === " ") && onSelect && !isLoading) {
      event.preventDefault();
      onSelect(race.id);
    }
  }

  const cardContent = (
    <>
      <div className="race-card__intro">
        <h3>{race.name}</h3>
        {isLoading && <span className="race-card__status">Loading</span>}
      </div>

      <div className="race-card__stat">
        <span className="race-card__label">Elapsed time</span>
        <strong>{race.elapsedTime}</strong>
      </div>

      <div className="race-card__stat">
        <span className="race-card__label">Distance</span>
        <strong>{race.distance}</strong>
      </div>

      <div className="race-card__stat">
        <span className="race-card__label">Foiling</span>
        <strong>{race.foilingPercentage}</strong>
      </div>

      <div className="race-card__stat">
        <span className="race-card__label">Maneuvers</span>
        <strong>{race.maneuvers}</strong>
      </div>

      {(onEdit || onDelete) && (
        <div className="race-card__actions">
          {onEdit && (
            <button
              type="button"
              className="secondary-button"
              onClick={(event) => handleActionClick(event, onEdit)}
            >
              Edit
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="ghost-button ghost-button--danger"
              onClick={(event) => handleActionClick(event, onDelete)}
            >
              Delete
            </button>
          )}
        </div>
      )}
    </>
  );

  if (onSelect) {
    return (
      <article
        className={`race-card race-card--button${isActive ? " race-card--active" : ""}`}
        role="button"
        tabIndex={isLoading ? -1 : 0}
        aria-disabled={isLoading}
        aria-pressed={isActive}
        onClick={() => {
          if (!isLoading) {
            onSelect(race.id);
          }
        }}
        onKeyDown={handleKeyDown}
      >
        {cardContent}
      </article>
    );
  }

  return (
    <article className={`race-card${isActive ? " race-card--active" : ""}`}>
      {cardContent}
    </article>
  );
}
