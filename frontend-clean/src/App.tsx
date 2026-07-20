import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

const Landing = lazy(() => import("./routes/Landing").then((module) => ({ default: module.Landing })));
const Login = lazy(() => import("./routes/Login").then((module) => ({ default: module.Login })));
const PlatformLayout = lazy(() =>
  import("./components/shell/PlatformLayout").then((module) => ({ default: module.PlatformLayout })),
);
const JobList = lazy(() => import("./routes/JobList").then((module) => ({ default: module.JobList })));
const BuildView = lazy(() => import("./routes/BuildView").then((module) => ({ default: module.BuildView })));
const RunMap = lazy(() => import("./routes/RunMap").then((module) => ({ default: module.RunMap })));
const Operations = lazy(() => import("./routes/Operations").then((module) => ({ default: module.Operations })));
const ProcessDetail = lazy(() =>
  import("./routes/ProcessDetail").then((module) => ({ default: module.ProcessDetail })),
);
const Sandbox = lazy(() => import("./routes/Sandbox").then((module) => ({ default: module.Sandbox })));
const Replay = lazy(() => import("./routes/Replay").then((module) => ({ default: module.Replay })));
const Config = lazy(() => import("./routes/Config").then((module) => ({ default: module.Config })));
const Traces = lazy(() => import("./routes/Traces").then((module) => ({ default: module.Traces })));

function RouteFallback() {
  return (
    <main
      role="status"
      aria-live="polite"
      aria-busy="true"
      style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}
    >
      Loading…
    </main>
  );
}

export function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route element={<PlatformLayout />}>
          <Route path="/build" element={<JobList />} />
          <Route path="/build/:jobId" element={<BuildView />} />
          <Route path="/build/:jobId/map" element={<RunMap />} />
          <Route path="/operations" element={<Operations />} />
          <Route path="/operations/:id" element={<ProcessDetail />} />
          <Route path="/gallery" element={<Navigate to="/build" replace />} />
          <Route path="/replay/:kind/:id" element={<Replay />} />
          <Route path="/sandbox" element={<Sandbox />} />
          <Route path="/config" element={<Config />} />
          <Route path="/traces" element={<Traces />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
