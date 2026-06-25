# Manual Tasks — do these before the demo

The app **runs without any of this** (every integration degrades to MOCK and
the vision subsystem synthesizes telemetry). These tasks make it real and
unlock the full demo. Priority order: dataset → Postgres → keys → SFX → voice.

---

## 0. First-time setup
```bash
cp .env.example .env            # then fill keys below
python -m venv .venv
. .venv/Scripts/activate        # Windows (bash: source .venv/bin/activate)
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

---

## 1. Vision dataset  *(done — 10 fish clips already extracted)*

- You supplied the **Brackish dataset** (Aalborg University), not the Zenodo
  tilapia set. 89 underwater videos categorized `fish-school` / `fish-big` /
  `crab` / `jellyfish` / etc., with **real COCO + YOLO annotations**.
- **Already handled:** 10 `fish-school` + `fish-big` clips extracted to
  `data/clips/` (25 MB). Vision broadcaster loops them as the "RTSP" stream.
- **No water-quality telemetry** in this dataset (its CSVs are bbox-tracking,
  not DO/pH/temp). So telemetry stays **synthetic** — the engine auto-generates
  plausible DO/pH/temp baseline values. Spec's `meta_tilapia_set.csv` is N/A.
- **Optional real YOLO:** annotations exist (`data/archive.zip` →
  `annotations/annotations_YOLO/*.txt` + `annotations_COCO/*.json`, classes
  `fish`/`small_fish`/...). To use: train YOLOv8, set `VISION_DETECTOR=yolo` +
  `VISION_YOLO_WEIGHTS=...`, `pip install ultralytics`. Default `motion`
  frame-differencing already detects 5–17 fish/clip reliably.

---

## 2. Postgres  *(persistence — telemetry/feed/audit logs)*
```bash
docker compose up -d postgres
```
On startup the backend auto-creates tables. If Postgres is down the app still
runs (logs a warning, skips persistence). No Neo4j needed — the causal graph
is in-process.

---

## 3. API keys  *(each optional — missing = MOCK)*

### OpenWeatherMap — ambient thermal drift (Context Agent)
- Sign up: https://openweathermap.org/api (free tier)
- `OPENWEATHER_API_KEY=...` (lat/lon for Puchong are pre-set: 3.0333, 101.6158)

### Telegram — async diagnostic alerts
- Create a bot via **@BotFather → /newbot** → copy token → `TELEGRAM_BOT_TOKEN`
- Get your chat id: message the bot, then:
  ```bash
  curl "https://api.telegram.org/bot<TOKEN>/getUpdates"   # read "chat":{"id":...}
  ```
- `TELEGRAM_CHAT_ID=<that id>`

### ElevenLabs — 3AM voice co-pilot  *(premium path; browser TTS is the fallback)*
- https://elevenlabs.io → Conversational AI → create an agent.
- `ELEVENLABS_API_KEY=...`, `ELEVENLABS_AGENT_ID=...`
- System prompt (already mirrored in `agents/action.py::VOICE_SYSTEM_PROMPT`):
  *"You are the AquaBro Emergency Bio-Security Officer. A critical hypoxia
  event has been detected in Tank 1. Inform the operator and ask whether to
  EXECUTE emergency aeration or CANCEL. Await their voice command."*
- **Tool:** add a server tool `trigger_aerator` whose webhook targets
  `{PUBLIC_BASE_URL}/api/hardware/override` with body
  `{"device":"aerator","action":"ACTIVE","reason":"voice_execute"}`.
- Expose locally via ngrok:
  ```bash
  ngrok http 8000
  # set PUBLIC_BASE_URL=https://<id>.ngrok-free.app  and  VOICE_ENABLED=true
  ```
- If you skip this, the voice overlay still appears and **speaks via browser
  SpeechSynthesis**, and the Execute button still fires the aerator webhook.
  So the climactic demo beat works either way.

---

## 4. SFX assets — "digital physicality" (spec §6.3)
Generate with ElevenLabs Text-to-SFX (or any source) and drop here:
```
frontend/public/sfx/pump.mp3    # "heavy industrial water pump spooling up"
frontend/public/sfx/valve.mp3   # "loud metallic pneumatic valve locking"
```
Missing files are silently skipped (the `playSfx` helper no-ops on error).

---

## 5. Run the demo
```bash
# terminal 1 — backend
uvicorn app.main:app --reload --app-dir backend      # http://localhost:8000

# terminal 2 — frontend
cd frontend && npm run dev                            # http://localhost:5173
```
Open http://localhost:5173. Either click the chaos buttons manually or hit
**Auto-Demo Narrator** to run the full 3-state script on a timer:
baseline → pH spike (toxicity → feed lock + Telegram) → reset →
DO crash (hypoxia → vision lethargy → aerator + voice) → reset.

---

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Vision panel says OFFLINE | no cv2 (`pip install opencv-python`) or no clips + no cv2 |
| Telemetry frozen at synthetic values | `meta_tilapia_set.csv` missing → synthetic baseline by design |
| No Telegram/voice | keys not set → MOCK mode (check backend logs for `[MOCK ...]`) |
| `postgres unavailable` log | `docker compose up -d postgres` not running |
| SSE not updating | ensure backend on :8000 (Vite proxies `/api` to it) |
