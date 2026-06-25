import { useEffect, useRef } from "react";
import type { NarrativeLine } from "../types";
import { fmtClock } from "../util";

/** Rolling plain-English account of what the system is seeing and doing. */
export default function NarrativeFeed({ lines }: { lines: NarrativeLine[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // newest at top — nothing to auto-scroll, but keep first item in view
    if (ref.current) ref.current.scrollTop = 0;
  }, [lines]);

  if (lines.length === 0) {
    return (
      <div className="card" style={{ flex: 1 }}>
        <div className="card-h">
          <span className="title">What's happening</span>
        </div>
        <div className="feed-empty">Waiting for the tank to report in…</div>
      </div>
    );
  }

  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-h">
        <span className="title">What's happening</span>
        <span className="meta">{lines.length} events</span>
      </div>
      <div className="feed-list" ref={ref}>
        {lines.map((l, i) => (
          <div className={`feed-item ${l.level === "info" ? "" : l.level}`} key={i}>
            <span className="marker" />
            <div className="body">
              <div className="text">{l.text}</div>
              <div className="time">{fmtClock(l.ts)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
