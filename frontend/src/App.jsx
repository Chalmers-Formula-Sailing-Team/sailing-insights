import { useDashboardController } from "./controllers/DashboardController.js";
import { DashboardView } from "./views/DashboardView.jsx";

export default function App() {
  const dashboardState = useDashboardController();

  return <DashboardView {...dashboardState} />;
}
