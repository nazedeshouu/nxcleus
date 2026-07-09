import { Routes, Route } from "react-router-dom";
import { Landing } from "./routes/Landing";
import { PlatformLayout } from "./components/shell/PlatformLayout";
import { JobList } from "./routes/JobList";
import { BuildView } from "./routes/BuildView";
import { Operations } from "./routes/Operations";
import { ProcessDetail } from "./routes/ProcessDetail";
import { Sandbox } from "./routes/Sandbox";
import { Gallery } from "./routes/Gallery";
import { Replay } from "./routes/Replay";
import { Config } from "./routes/Config";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<PlatformLayout />}>
        <Route path="/build" element={<JobList />} />
        <Route path="/build/:jobId" element={<BuildView />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/operations/:id" element={<ProcessDetail />} />
        <Route path="/gallery" element={<Gallery />} />
        <Route path="/replay/:kind/:id" element={<Replay />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/config" element={<Config />} />
      </Route>
    </Routes>
  );
}
