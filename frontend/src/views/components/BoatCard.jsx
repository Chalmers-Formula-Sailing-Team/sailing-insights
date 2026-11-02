export function BoatCard({ boat, onSelect, onEdit, onDelete }) {
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
      className="boat-card boat-card--interactive"
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
    >
      <div className="boat-card__image-wrap">
        <img className="boat-card__image" src={boat.image} alt={boat.name} />
      </div>
      <div className="boat-card__content">
        <div className="boat-card__header">
          <div>
            <p className="boat-card__class">{boat.className}</p>
            <h3>{boat.name}</h3>
            {boat.sailNumber && <p className="boat-card__sailnumber">{boat.sailNumber}</p>}
          </div>
          <span className="boat-card__hours">{boat.hoursLabel}</span>
        </div>
        <div className="boat-card__meta">
          <span>{boat.sessionCount} sessions</span>
          <span>Distance: {boat.distanceNm.toFixed(1)} nm</span>
        </div>
        <div className="boat-card__actions">
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
      </div>
    </article>
  );
}
