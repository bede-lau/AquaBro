interface Props {
  powered: boolean;
  onPower: (on: boolean) => void;
  onSpike: (cmd: { do?: number; ph?: number; temp_c?: number }) => void;
  onReset: () => void;
}

/** Master power + manual fault injection. Power off ⇒ system stops tracking
 *  and the log goes quiet; fault buttons are disabled until it's running. */
export default function DemoBar({ powered, onPower, onSpike, onReset }: Props) {
  return (
    <div className="demobar">
      <span className="lbl">System</span>
      <button
        className={`btn primary sm ${powered ? "" : "pulse"}`}
        disabled={powered}
        onClick={() => onPower(true)}
      >▶ Start system</button>
      <button className="btn ghost sm" disabled={!powered} onClick={() => onPower(false)}>■ Stop</button>

      <span className="sep" />

      <span className="lbl">Inject fault</span>
      <button className="btn feed sm" disabled={!powered} onClick={() => onSpike({ ph: 8.7 })}>pH spike</button>
      <button className="btn danger sm" disabled={!powered} onClick={() => onSpike({ do: 1.2 })}>O₂ crash</button>
      <button className="btn ghost sm" disabled={!powered} onClick={onReset}>Reset</button>

      <span style={{ flex: 1 }} />
      <span className={`pill ${powered ? "good" : "warn"}`}>
        <span className="led" /> {powered ? "RUNNING" : "OFFLINE"}
      </span>
    </div>
  );
}
