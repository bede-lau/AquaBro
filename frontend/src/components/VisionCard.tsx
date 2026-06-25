import type { VisionAssessment } from "../types";
import { activityLabel } from "../util";

export default function VisionCard({ vision }: { vision: VisionAssessment | null }) {
  const live = vision != null && !vision.fault;
  const n = vision?.fish_count ?? 0;
  return (
    <div className="card">
      <div className="card-h">
        <span className="title">Tank camera</span>
        <span className="meta">{live ? "live" : "offline"}</span>
      </div>
      <div className="vision-frame">
        {live ? (
          <img src="/api/vision/stream" alt="live tank feed" />
        ) : (
          <div className="vision-off">camera offline</div>
        )}

        {/* prominent fish-count badge — the key CV readout */}
        <div className={`fish-badge ${live ? "" : "off"}`}>
          <span className="fish-count">{n}</span>
          <span className="fish-label">fish detected</span>
        </div>

        <div className="activity-chip">
          activity · <b>{activityLabel(vision?.activity_index)}</b>
        </div>
      </div>
    </div>
  );
}
