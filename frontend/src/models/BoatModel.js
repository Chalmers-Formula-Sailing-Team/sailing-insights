import { SessionModel } from "./SessionModel.js";

export class BoatModel {
  constructor(boat) {
    this.boat = boat;
    this.sessions = boat.sessions.map((session) => new SessionModel(session));
  }

  get id() {
    return this.boat.id;
  }

  get hours() {
    return this.boat.hours;
  }

  get distanceNm() {
    return this.boat.distanceNm;
  }

  get sessionCount() {
    return this.sessions.length;
  }

  get totalDurationHours() {
    return this.sessions.reduce((sum, session) => sum + session.durationHours, 0);
  }

  get totalSessionDistanceNm() {
    return this.sessions.reduce((sum, session) => sum + session.distanceNm, 0);
  }

  get maxSpeedKts() {
    if (this.sessions.length === 0) {
      return 0;
    }

    return Math.max(...this.sessions.map((session) => session.maxSpeedKts));
  }

  get averageFoilingPercent() {
    const totalDurationHours = this.totalDurationHours;
    const weightedFoiling = this.sessions.reduce(
      (sum, session) => sum + session.foilingPercent * session.durationHours,
      0
    );

    return totalDurationHours === 0 ? 0 : weightedFoiling / totalDurationHours;
  }

  get totalCapsizes() {
    return this.sessions.reduce((sum, session) => sum + session.capsizes, 0);
  }

  toListItemViewData() {
    return {
      ...this.boat,
      maxSpeedKts: this.maxSpeedKts,
      hoursLabel: `${this.boat.hours.toFixed(1)} hours`,
      sessionCount: this.sessionCount,
    };
  }

  toDetailViewData() {
    return {
      boat: {
        ...this.boat,
        hoursLabel: `${this.boat.hours.toFixed(1)} hours`,
      },
      summary: {
        totalTime: `${this.totalDurationHours.toFixed(1)} h`,
        totalDistance: `${this.totalSessionDistanceNm.toFixed(1)} nm`,
        maxSpeed: `${this.maxSpeedKts.toFixed(1)} kn`,
        sessionsAmount: `${this.sessionCount}`,
        averageFoiling: `${this.averageFoilingPercent.toFixed(0)}%`,
        capsizes: `${this.totalCapsizes}`,
      },
      sessions: this.sessions.map((session) => session.toViewData()),
    };
  }

  getSessionDetail(sessionId) {
    const session = this.sessions.find((item) => item.session.id === sessionId);

    if (!session) {
      return null;
    }

    return {
      boat: this.toListItemViewData(),
      session: session.toDetailViewData(),
    };
  }
}
