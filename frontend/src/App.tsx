import { Routes, Route } from "react-router-dom";
import { Landing } from "./routes/Landing";
import { PlatformLayout } from "./components/shell/PlatformLayout";
import { JobList } from "./routes/JobList";
import { BuildView } from "./routes/BuildView";
import { Placeholder } from "./routes/Placeholder";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<PlatformLayout />}>
        <Route path="/build" element={<JobList />} />
        <Route path="/build/:jobId" element={<BuildView />} />
        <Route
          path="/operations"
          element={<Placeholder title="Operations" note="The process registry — versions, runs, cost trend, warranty. Wave 2." />}
        />
        <Route
          path="/gallery"
          element={<Placeholder title="Gallery" note="Five rehearsed demos with live seed kits. Wave 2." />}
        />
        <Route
          path="/sandbox"
          element={<Placeholder title="Judge sandbox" note="Three synthetic companies with browsable mock data. Every run is a real process-mode job. Wave 2." />}
        />
      </Route>
    </Routes>
  );
}
