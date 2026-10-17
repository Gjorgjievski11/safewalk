# Safe Walk Skopje

Walking in Skopje after dark is an obstacle course: cars on sidewalks, bushes on the path, streets with no light. Upload a photo of the problem, it gets categorized and pinned on a map, and a "safer route" bends around the pins.

Built for Hacktoberfest 2026 (Fix My City).

## How it works

| Part | What does it | Model or rule? |
|---|---|---|
| Photo category | CLIP zero-shot (ViT-B/32) | Model |
| Darkness | Mean image brightness | Rule |
| Broken streetlight | Picked by the user | Manual |
| Report text (Macedonian) | gpt-oss via OpenRouter, template fallback | Model |
| Safer route | OSM street graph + penalty per nearby pin (networkx) | Algorithm |
| Hotspots | Pins grouped by street | Rule |

Demo data in `data/seed.json` is seeded, so the app is a prototype.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- git
- An OpenRouter API key (free): https://openrouter.ai/keys

## Setup

```bash
git clone git@github.com:<your-username>/safewalk.git
cd safewalk
uv sync
cp .env.example .env     # Windows PowerShell: copy .env.example .env
```

Then put your key in `.env`:

```
OPENROUTER_API_KEY=sk-or-...
```

Without a key the app still works and uses a template for the report text.

### Pre-download the CLIP weights (do this before the event, ~350 MB)

```bash
uv run python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k'); print('clip cached')"
```

### Check the install

```bash
uv run python -c "import osmnx, networkx, fastapi, open_clip; print('ok')"
```

## Run

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. Health check: http://localhost:8000/health

### Using it from a phone

Connect the phone to the same wifi or hotspot and open `http://<your-laptop-ip>:8000`.
Browsers block geolocation on plain HTTP, so tap the map to set the pin location. For HTTPS, run:

```bash
cloudflared tunnel --url http://localhost:8000
```

### Windows notes

- Use PowerShell, not cmd.
- Allow Python through the firewall when prompted, otherwise phones can't connect.
- Run `git config core.autocrlf input` once.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/classify` | Image in, `{label, confidence, brightness}` out |
| POST | `/reports` | Save a report, returns the drafted text |
| GET | `/reports` | All pins |
| GET | `/route?from=lat,lon&to=lat,lon` | Direct and safer route |
| GET | `/hotspots` | Worst streets |
| GET | `/export.csv` | Reports as CSV |

Labels: `parked_on_sidewalk`, `overgrown`, `dark_street`, `broken_light`, `none`.

## Project layout

```
app/
  main.py       FastAPI app and routes
  classify.py   CLIP zero-shot and brightness
  drafting.py   report text (OpenRouter + template fallback)
  routing.py    OSM graph and safer-route logic
  db.py         SQLite storage
static/         frontend (Leaflet + Tailwind, served by FastAPI)
data/           OSM graph (.graphml) and seed.json
tests/photos/   sample photos for tuning the classifier
uploads/        user uploads (not committed)
```

## Roadmap

- Voice input in Macedonian (Whisper fine-tunes)
- Public transit layer from the JSP Skopje GTFS feed
- Safe points and buddy check-in for walking at night
- Local Macedonian LLM (VezilkaLLM) instead of an API
- CSV export for anyone who wants to pressure the city

## License

MIT