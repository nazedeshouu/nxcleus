import { GraphicsCard } from "@phosphor-icons/react";
import { Panel } from "./Panel";
import type { JobView } from "../../store/jobStore";
import type { TelemetryGpuPayload } from "../../lib/events";

export function Telemetry({ view }: { view: JobView }) {
  const gpus = Object.values(view.telemetry).sort((a, b) =>
    a.node === b.node ? a.gpu - b.gpu : a.node.localeCompare(b.node)
  );
  const active = view.stage >= 1 && view.status !== "done";

  return (
    <Panel
      title="AMD MI300X telemetry"
      icon={GraphicsCard}
      status={active && gpus.length ? "active" : gpus.length ? "ok" : "pending"}
      tag={gpus.length ? `${gpus.length} GPU` : "ROCm · vLLM"}
    >
      {gpus.length === 0 && (
        <p className="bv-goal-pending" style={{ fontSize: "var(--fs-sm)" }}>
          Live per-GPU utilization streams once the fleet is provisioned.
        </p>
      )}
      <div className="bv-gpu-list">
        {gpus.map((g: TelemetryGpuPayload) => {
          const vramPct = (g.vram_used_gb / g.vram_total_gb) * 100;
          return (
            <div className="bv-gpu" key={`${g.node}#${g.gpu}`}>
              <div className="bv-gpu-top">
                <span className="bv-gpu-node">
                  {g.node.replace("amd-mi300x-", "node ")}
                  {g.gpus ? ` · ${g.gpus}× MI300X` : ` · gpu${g.gpu}`}
                </span>
                <span className="bv-gpu-toks tnum">{g.toks_per_s.toLocaleString()} tok/s</span>
              </div>
              <div className="bv-gpu-bars">
                <div>
                  <div className="bv-gpu-metric-lbl">util <b className="tnum">{g.util}%</b></div>
                  <div className="bv-gpu-track"><div className="bv-gpu-fill util" style={{ width: `${g.util}%` }} /></div>
                </div>
                <div>
                  <div className="bv-gpu-metric-lbl">vram <b className="tnum">{g.vram_used_gb.toFixed(0)}/{g.vram_total_gb}G</b></div>
                  <div className="bv-gpu-track"><div className="bv-gpu-fill vram" style={{ width: `${vramPct}%` }} /></div>
                </div>
              </div>
              <div className="bv-gpu-power tnum">{g.power_w} W</div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
