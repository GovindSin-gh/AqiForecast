import { NavLink, Route, Routes } from "react-router-dom";
import MapPage from "./pages/MapPage.jsx";
import CityPage from "./pages/CityPage.jsx";
import HealthPage from "./pages/HealthPage.jsx";

export default function App() {
  return (
    <>
      <header className="top">
        <strong>AQI Forecast</strong>
        <nav aria-label="Main">
          <NavLink to="/" end>Map</NavLink>
          <NavLink to="/health">Model health</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/city/:id" element={<CityPage />} />
          <Route path="/health" element={<HealthPage />} />
        </Routes>
      </main>
    </>
  );
}
