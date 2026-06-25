import type { TankState } from "../types";
import { FSM_META } from "../util";
import type { TelegramStatus } from "../api";

export default function StatusPill({
  tank,
  telegram,
}: {
  tank: TankState | null;
  telegram: TelegramStatus | null;
}) {
  const fsm = tank
    ? FSM_META[tank.fsm_state] ?? { cls: "ok" as const, label: tank.fsm_state }
    : { cls: "ok" as const, label: "Connecting" };

  return (
    <>
      <span className={`pill ${fsm.cls}`}>
        <span className="led" />
        {fsm.label}
      </span>
      {telegram && (
        <span className={`pill ${telegram.ready ? "good" : ""}`} title="Telegram operator agent">
          <span className="led" />
          {telegram.ready ? `Bot online · ${telegram.model}` : "Bot off"}
        </span>
      )}
    </>
  );
}
