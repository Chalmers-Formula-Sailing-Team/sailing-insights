function MaterialIcon({ name, label }) {
  return (
    <span className="material-icons" aria-hidden="true" title={label}>
      {name}
    </span>
  );
}

export function StopwatchIcon() {
  return <MaterialIcon name="timer" label="Time" />;
}

export function DistanceIcon() {
  return <MaterialIcon name="timeline" label="Distance" />;
}

export function SpeedIcon() {
  return <MaterialIcon name="flash_on" label="Speed" />;
}

export function SessionsIcon() {
  return <MaterialIcon name="event_note" label="Sessions" />;
}

export function FoilingIcon() {
  return <MaterialIcon name="flight" label="Foiling" />;
}

export function CapsizeIcon() {
  return <MaterialIcon name="refresh" label="Capsizes" />;
}
