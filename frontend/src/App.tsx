import { Routes, Route, Navigate } from "react-router-dom";
import { Landing } from "./routes/Landing";
import { PlatformLayout } from "./components/shell/PlatformLayout";
import { JobList } from "./routes/JobList";
import { BuildView } from "./routes/BuildView";
import { Operations } from "./routes/Operations";
import { ProcessDetail } from "./routes/ProcessDetail";
import { Sandbox } from "./routes/Sandbox";
import { Replay } from "./routes/Replay";
import { Config } from "./routes/Config";
import { Traces } from "./routes/Traces";
import { Login } from "./routes/Login";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route element={<PlatformLayout />}>
        <Route path="/build" element={<JobList />} />
        <Route path="/build/:jobId" element={<BuildView />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/operations/:id" element={<ProcessDetail />} />
        <Route path="/gallery" element={<Navigate to="/build" replace />} />
        <Route path="/replay/:kind/:id" element={<Replay />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/config" element={<Config />} />
        <Route path="/traces" element={<Traces />} />
      </Route>
    </Routes>
  );
}
