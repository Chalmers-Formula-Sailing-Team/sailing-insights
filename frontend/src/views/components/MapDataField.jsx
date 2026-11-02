function formatChannelName(name) {
  if (name === "boat_speed") {
    return "SOG";
  }

  if (name === "twd_external") {
    return "External wind direction";
  }

  if (name === "tws_external") {
    return "External wind speed";
  }

  if (name === "twg_external") {
    return "External wind gust";
  }

  if (name === "time_rel_s") {
    return "Relative time";
  }

  if (name === "height_m") {
    return "Ride height";
  }

  return String(name || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatMinutesAndSeconds(value) {
  const safeTotalSeconds = Math.max(Math.round(Number(value) || 0), 0);
  const totalMinutes = Math.floor(safeTotalSeconds / 60);
  const seconds = safeTotalSeconds % 60;
  return `${totalMinutes}:${String(seconds).padStart(2, "0")}`;
}

function formatChannelValue(value, channelName) {
  if (value === null || value === undefined) {
    return "-";
  }

  if (typeof value === "number") {
    if (channelName === "ttg") {
      return formatMinutesAndSeconds(value);
    }

    if (channelName === "lat" || channelName === "lon") {
      return value.toFixed(6);
    }

    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  if (typeof value === "boolean") {
    return value ? "True" : "False";
  }

  return String(value);
}

function shouldShowChannelUnit(value, channel) {
  if (value === null || value === undefined || !channel.unit) {
    return false;
  }

  return channel.name !== "ttg";
}

export function MapDataField({ channel, value }) {
  return (
    <article className="map-data-field">
      <p className="map-data-field__label">{formatChannelName(channel.name)}</p>
      <strong className="map-data-field__value">
        {formatChannelValue(value, channel.name)}
        {shouldShowChannelUnit(value, channel) && (
          <span>{channel.unit}</span>
        )}
      </strong>
    </article>
  );
}
