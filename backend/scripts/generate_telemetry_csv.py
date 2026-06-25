"""Generate a synthetic Tilapia-RAS telemetry CSV for the demo.

The real Zenodo ``meta_tilapia_set.csv`` ships inside a 172 MB archive that
isn't always extracted. This script writes a believable healthy baseline
(DO / pH / temp) so ``TelemetrySource`` replays structured data instead of the
in-memory sine fallback. The Demo-Chaos panel injects the dangerous states at
showtime, so the baseline just needs to look stable and realistic.

Run:
    python backend/scripts/generate_telemetry_csv.py
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "meta_tilapia_set.csv"

ROWS = 600          # 12 min of replay at the default 1.2s cadence
CADENCE_S = 1.2
SEED = 42


def main() -> None:
    rnd = random.Random(SEED)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        # Header tokens match the auto-detection in engine.TelemetrySource
        # ("do" / "ph_" / "temp").
        w.writerow(["timestamp", "do_level", "ph_level", "temp_c"])
        for i in range(ROWS):
            t = i * CADENCE_S
            # Healthy intensive-RAS tilapia band: DO 6.4–7.5, pH 7.05–7.30, ~28.5°C.
            do = 6.95 + 0.30 * math.sin(t * 0.05) + rnd.uniform(-0.15, 0.15)
            ph = 7.18 + 0.035 * math.sin(t * 0.03 + 0.7) + rnd.uniform(-0.02, 0.02)
            temp = 28.5 + 0.20 * math.sin(t * 0.02 + 1.3) + rnd.uniform(-0.10, 0.10)
            do = max(6.3, min(7.6, do))
            ph = max(7.0, min(7.35, ph))
            temp = max(27.8, min(29.2, temp))
            mins, secs = divmod(int(t), 60)
            w.writerow([f"00:{mins:02d}:{secs:02d}",
                        f"{do:.3f}", f"{ph:.3f}", f"{temp:.3f}"])

    print(f"wrote {ROWS} rows -> {OUT}")


if __name__ == "__main__":
    main()
