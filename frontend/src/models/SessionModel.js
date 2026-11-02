import { projectTrackPoints } from "../utils/trackMap.js";

export class SessionModel {
  constructor(session) {
    this.session = session;
  }

  clampFoilingPercent(value) {
    return Math.min(Math.max(value, 0), 100);
  }

  formatPercentage(value) {
    const safeValue = this.clampFoilingPercent(value);
    return `${safeValue.toFixed(1)}%`;
  }

  buildManeuverFoilingChart({
    title,
    totalCount,
    foilingCount,
    foilingPercentage,
    activeColor,
    inactiveColor,
  }) {
    const safeTotalCount = Math.max(0, Math.round(Number(totalCount) || 0));
    const safeFoilingCount = Math.min(
      safeTotalCount,
      Math.max(0, Math.round(Number(foilingCount) || 0))
    );
    const safeFoilingPercentage = this.clampFoilingPercent(foilingPercentage);

    return {
      title,
      centerValue: this.formatPercentage(safeFoilingPercentage),
      subtitle:
        safeTotalCount > 0
          ? `${safeFoilingCount} of ${safeTotalCount} foiling`
          : "No maneuvers recorded",
      segments: [
        {
          label: "Foiling",
          value: safeFoilingPercentage,
          color: activeColor,
        },
        {
          label: "Non-foiling",
          value: Math.max(0, 100 - safeFoilingPercentage),
          color: inactiveColor,
        },
      ],
    };
  }

  formatDurationLabel({ includeLowerUnit = false } = {}) {
    if (!includeLowerUnit) {
      const totalMinutes = Math.round(this.session.durationHours * 60);
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;

      if (minutes === 0) {
        return `${hours}h`;
      }

      return `${hours}h ${minutes}m`;
    }

    const totalSeconds = Math.max(Math.round(this.session.durationHours * 3600), 0);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }

    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }

    return `${seconds}s`;
  }

  get durationHours() {
    return this.session.durationHours;
  }

  get distanceNm() {
    return this.session.distanceNm;
  }

  get maxSpeedKts() {
    return this.session.maxSpeedKts;
  }

  get tacks() {
    return this.session.tacks;
  }

  get gybes() {
    return this.session.gybes;
  }

  get foilingPercent() {
    return this.session.foilingPercent;
  }

  get foilingTimeMin() {
    return this.session.foilingTimeMin;
  }

  get capsizes() {
    return this.session.capsizes;
  }

  formatMinutes(totalMinutes) {
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;

    if (hours === 0) {
      return `${minutes}m`;
    }

    if (minutes === 0) {
      return `${hours}h`;
    }

    return `${hours}h ${minutes}m`;
  }

  formatConditionValue(value, unit, fractionDigits = 0) {
    if (!Number.isFinite(value)) {
      return "No data";
    }

    if (fractionDigits === 0) {
      return `${Math.round(value)} ${unit}`;
    }

    return `${value.toFixed(fractionDigits)} ${unit}`;
  }

  toViewData() {
    return {
      ...this.session,
      durationLabel: this.formatDurationLabel(),
      distanceLabel: `${this.session.distanceNm.toFixed(1)} nm`,
      maxSpeedLabel: `${this.session.maxSpeedKts.toFixed(1)} kn`,
      windLabel: `${this.session.windStrengthKts} kn ${this.session.windDirection}`,
      foilingLabel: this.formatPercentage(this.session.foilingPercent),
      foilingTimeLabel: this.formatMinutes(Math.round(this.session.foilingTimeMin)),
    };
  }

  toDetailViewData() {
    const totalMinutes = Math.round(this.session.durationHours * 60);
    const projectedTrackPoints = projectTrackPoints(this.session.trackPoints);
    const trackPoints = projectedTrackPoints.map((point, index, points) => {
      const elapsedMinutes = Math.round(
        (index / Math.max(points.length - 1, 1)) * totalMinutes
      );

      return {
        ...point,
        elapsedMinutes,
        elapsedLabel: this.formatMinutes(elapsedMinutes),
      };
    });

    return {
      ...this.toViewData(),
      summary: {
        duration: this.formatDurationLabel({ includeLowerUnit: true }),
        distance: `${this.session.distanceNm.toFixed(1)} nm`,
        maxSpeed: `${this.session.maxSpeedKts.toFixed(1)} kn`,
        foilingTime: this.formatMinutes(Math.round(this.session.foilingTimeMin)),
        foilingAverage: this.formatPercentage(this.session.foilingPercent),
        tacks: `${this.session.tacks}`,
        gybes: `${this.session.gybes}`,
        capsizes: `${this.session.capsizes}`,
      },
      conditions: [
        {
          title: "Manual entry",
          items: [
            {
              label: "Wind",
              icon: "air",
              value: this.formatConditionValue(
                this.session.manualWindStrengthKts,
                "kn"
              ),
            },
            {
              label: "Gusts",
              icon: "flash_on",
              value: this.formatConditionValue(
                this.session.manualGustsKts,
                "kn"
              ),
            },
            {
              label: "Wind dir",
              icon: "explore",
              value: this.formatConditionValue(
                this.session.manualWindDirectionDeg,
                "deg"
              ),
            },
            {
              label: "Wave height",
              icon: "waves",
              value: this.formatConditionValue(
                this.session.manualWaveHeightM,
                "m",
                1
              ),
            },
          ],
        },
        {
          title: "External data",
          items: [
            {
              label: "Wind",
              icon: "air",
              value: this.formatConditionValue(
                this.session.externalWindStrengthKts,
                "kn"
              ),
            },
            {
              label: "Gusts",
              icon: "flash_on",
              value: this.formatConditionValue(
                this.session.externalGustsKts,
                "kn"
              ),
            },
            {
              label: "Wind dir",
              icon: "explore",
              value: this.formatConditionValue(
                this.session.externalWindDirectionDeg,
                "deg"
              ),
            },
            {
              label: "Wave height",
              icon: "waves",
              value: "No data",
            },
          ],
        },
      ],
      foilingChart: {
        title: "Foiling time",
        centerValue: this.formatPercentage(this.session.foilingPercent),
        subtitle: `${this.formatMinutes(Math.round(this.session.foilingTimeMin))} total fly time`,
        segments: [
          {
            label: "Foiling",
            value: this.clampFoilingPercent(this.session.foilingPercent),
            color: "#0f766e",
          },
          {
            label: "Displacement",
            value: Math.max(0, 100 - this.clampFoilingPercent(this.session.foilingPercent)),
            color: "#d7e7e2",
          },
        ],
      },
      foilingTackChart: this.buildManeuverFoilingChart({
        title: "Foiling tacks",
        totalCount: this.session.tacks,
        foilingCount: this.session.foilingTacks,
        foilingPercentage: this.session.foilingTackPercentage,
        activeColor: "#0f766e",
        inactiveColor: "#d7e7e2",
      }),
      foilingGybeChart: this.buildManeuverFoilingChart({
        title: "Foiling gybes",
        totalCount: this.session.gybes,
        foilingCount: this.session.foilingGybes,
        foilingPercentage: this.session.foilingGybePercentage,
        activeColor: "#c56a1b",
        inactiveColor: "#f3dfc7",
      }),
      replay: {
        durationLabel: this.formatDurationLabel(),
        trackPoints,
      },
    };
  }
}
