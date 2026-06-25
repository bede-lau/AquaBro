import type { TankState } from "../types";
import type { Cls } from "../util";
import { activityLabel, doClass, nh3Class, phClass, tempClass } from "../util";

function Vital({
  k, v, u, cls, note, chip,
}: {
  k: string; v: string; u?: string; cls: Cls; note?: string; chip?: { cls: Cls; text: string };
}) {
  return (
    <div className={`vital ${cls}`}>
      <div className="k">{k}</div>
      <div className="v">{v}{u && <span className="u">{u}</span>}</div>
      {note && <div className="note">{note}</div>}
      {chip && <span className={`chip ${chip.cls}`}>{chip.text}</span>}
    </div>
  );
}

/** The few life-signs that actually matter to a site operator. */
export default function Vitals({ state }: { state: TankState | null }) {
  const t = state?.telemetry;
  const tox = state?.toxicity;
  const vis = state?.vision;
  const fault = !!state?.sensor_fault;

  const doCls = t ? doClass(t.do_level, fault) : "ok";
  const phCls = t ? phClass(t.ph_level) : "ok";
  const tmpCls = t ? tempClass(t.temp_c) : "ok";
  const nh3 = tox?.nh3_mg_l;
  const nh3Cls = nh3 != null ? nh3Class(nh3, tox?.threshold_mg_l, !!tox?.toxic) : "ok";

  return (
    <div className="card">
      <div className="card-h">
        <span className="title">Tank vitals</span>
        <span className="meta">{t?.tank_id ?? "TANK-01"}</span>
      </div>
      <div className="vitals">
        <Vital
          k="Ammonia · NH₃"
          v={nh3 != null ? nh3.toFixed(3) : "--"}
          u="mg/L"
          cls={nh3Cls}
          note={tox ? `TAN ${tox.tan.toFixed(2)} mg/L` : undefined}
          chip={nh3 != null ? { cls: nh3Cls, text: nh3Cls === "crit" ? "toxic" : nh3Cls === "warn" ? "rising" : "safe" } : undefined}
        />
        <Vital
          k="Dissolved O₂"
          v={t ? t.do_level.toFixed(2) : "--"}
          u="mg/L"
          cls={doCls}
          chip={t ? { cls: doCls, text: doCls === "crit" ? "low" : doCls === "warn" ? "watch" : "good" } : undefined}
        />
        <Vital
          k="pH"
          v={t ? t.ph_level.toFixed(2) : "--"}
          cls={phCls}
          chip={t ? { cls: phCls, text: phCls === "crit" ? "high" : phCls === "warn" ? "drift" : "steady" } : undefined}
        />
        <Vital
          k="Temperature"
          v={t ? t.temp_c.toFixed(1) : "--"}
          u="°C"
          cls={tmpCls}
          note={vis ? `${vis.fish_count} fish · ${activityLabel(vis.activity_index)}` : undefined}
          chip={t ? { cls: tmpCls, text: tmpCls === "crit" ? "hot" : tmpCls === "warn" ? "warm" : "ok" } : undefined}
        />
      </div>
      {fault && (
        <div className={`pill crit`} style={{ marginTop: 12 }}>
          <span className="led" /> Oxygen probe fault — holding last good reading
        </div>
      )}
    </div>
  );
}
