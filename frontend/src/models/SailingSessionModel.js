import { BoatModel } from "./BoatModel.js";

export class SailingSessionModel {
  constructor({ sailorName, sessionWindow, boats }) {
    this.sailorName = sailorName;
    this.sessionWindow = sessionWindow;
    this.boats = boats.map((boat) => new BoatModel(boat));
  }

  getFleetSummary() {
    const totalHours = this.boats.reduce((sum, boat) => sum + boat.hours, 0);
    const totalDistanceNm = this.boats.reduce(
      (sum, boat) => sum + boat.distanceNm,
      0
    );

    return {
      sailorName: this.sailorName,
      sessionWindow: this.sessionWindow,
      totalHours: `${totalHours.toFixed(1)} h`,
      totalDistanceNm: `${totalDistanceNm.toFixed(1)} nm`,
      boatCount: this.boats.length,
    };
  }

  getBoats() {
    return this.boats.map((boat) => boat.toListItemViewData());
  }

  getBoatDetail(boatId) {
    const boat = this.boats.find((item) => item.id === boatId);

    if (!boat) {
      return null;
    }

    return boat.toDetailViewData();
  }

  getSessionDetail(boatId, sessionId) {
    const boat = this.boats.find((item) => item.id === boatId);

    if (!boat) {
      return null;
    }

    return boat.getSessionDetail(sessionId);
  }
}
