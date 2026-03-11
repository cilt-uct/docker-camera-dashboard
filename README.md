
# Docker Camera Dashboard 

**Dockerized services to capture images from RTSP cameras, generate timelapse, and serve a simple API/UI to view feeds.**

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quickstart (Docker Compose)](#quickstart-docker-compose)
- [Configuration](#configuration)
- [How it works](#how-it-works)
- [API / Endpoints](#api--endpoints)
- [Development & Running Locally](#development--running-locally)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This project captures periodic still images from RTSP cameras, stores images to a shared volume, generates timelapse, and exposes a small HTTP API + UI to view the latest images and timelapses. It is designed to run via Docker Compose and uses Redis for lightweight coordination/status.

✅ Ideal for monitoring multiple fixed cameras where streaming full video is heavy or unnecessary.

---

## Architecture

- **capture_service** — scheduled job that polls cameras, uses `ffmpeg` to capture images and to generate Webm+MP4 timelapses.
- **ui_service** — FastAPI service that exposes endpoints for listing cameras, viewing the latest image and timelapse, and basic health/status.
- **redis** — used to store start times and simple status information.
- **opencast** client** — small client to fetch cameras from an Opencast server (optional integration).

All services share a `shared_volume` that contains `images/` and `timelapse/` for the UI to serve static assets.

---

## Prerequisites

- Docker & Docker Compose (v2) installed
- `ffmpeg` available in the `capture_service` Docker image (already used in scripts)
- Optional: access to an Opencast server for camera discovery

---

## Quickstart (Docker Compose)

1. Copy or create a `.env` file in the repository root (see **Configuration** below). You can use the provided example:

```bash
cp .env.example .env
```

2. Place secret files referenced by `docker-compose.yml` (e.g., the `passwords` file and `redis_password`). Examples are in the `secrets/` folder:

```bash
# Copy example secrets to where Docker Compose expects them (adjust paths or compose files as needed)
cp secrets/passwords.example /usr/local/serverconfig/camera_dashboard.cfg
cp secrets/redis_password.example /usr/local/serverconfig/camera_dashboard_redis_password
```

Alternatively, point the secrets to a local path or override `docker-compose.yml` for development.

3. Build and run:

```bash
docker-compose up --build -d
```

4. Visit the UI/API at `http://<host>:8000` (FastAPI routes are mounted there).

To view container logs:

```bash
docker-compose logs -f ui_service
docker-compose logs -f capture_service
```

---

## Configuration

Configuration is handled via environment variables and a pydantic settings class located in `utils/settings.py` (class `FetchSettings`). Key variables:

- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `OC_SERVER`, `OC_USER`, `OC_PASS` — Opencast integration
- `IMAGE_DIR` (default: `/shared_volume/images`)
- `TIMELAPSE_DIR` (default: `/shared_volume/timelapse`)
- `CAPTURE_INTERVAL`, `TIMELAPSE_INTERVAL`, `CLEAN_INTERVAL`
- `BATCH_SIZE`, `BATCH_DELAY`

Compose uses secrets for Redis and service passwords as configured in `docker-compose.yml`.

> Tip: The settings accept boolean env vars like `true`/`false` or `1`/`0`.

---

## How it works

- `capture_service/scheduler.py` runs APScheduler to periodically:
  - Capture still images for configured cameras (via `capture_images.sh` which uses `ffmpeg`).
  - Generate timelapses from recent images using `generate_timelapse.sh`.
  - Clean up images older than the configured `CLEAN_INTERVAL`.

- Image capture uses the helper script `capture_images.sh` which overlays a timestamp and writes the JPG to the camera-specific folder under `/shared_volume/images`.

- Timelapse generation picks the most recent images (last ~288 by default) and uses `ffmpeg` to compile a Webm+MP4 in `/shared_volume/timelapse`.

- `ui_service` serves the `shared_volume` statically at `/static` and exposes API routes to list cameras and get current image / timelapse URLs.

---

## Cameras configuration

Cameras are now decoupled from the code and are loaded (in order of preference) from:

1. A JSON file specified by `CAMERAS_FILE` (default: `/run/secrets/cameras.json`) — place your camera list here and keep it out of version control (there is an example at `secrets/cameras.json.example`).
2. A Redis key specified with `CAMERAS_REDIS_KEY` (default: `camera_list`) — useful to update the list at runtime.
3. The built-in `DEFAULT_CAMERAS` fallback.

The cameras file should contain a JSON array of objects with the shape:

```json
[
  { "name": "room1", "rtsp_url": "rtsp://room1.local/cam01/axis-media/media.amp" }
]
```

### Import from Opencast

We provide a helper to import cameras from an Opencast server and save them to Redis:

```bash
# Fetch cameras from Opencast and store in Redis
python opencast/update_cameras.py
```

This will call your Opencast instance (configured via `OC_SERVER`, `OC_USER`, `OC_PASS`) and write the returned list to the Redis key declared in `CAMERAS_REDIS_KEY`.

To refresh the cameras used by services after updating Redis, either restart the services or call the `refresh_cameras()` helper in `utils.settings` (e.g., from a shell script or a management command).

---

---

## API / Endpoints

- GET `/` — list all cameras with current image and timelapse URLs
- GET `/{camera_name}/current` — JSON containing `image_url` for the latest image
- GET `/{camera_name}/timelapse` — JSON containing `image_url` for the timelapse
- GET `/opencast/cameras` — fetch cameras from configured Opencast server (if available)
- GET `/status` — service status information

Examples:

```bash
curl http://localhost:8000/status
curl http://localhost:8000/ -s | jq .
```

---

## Development & Running Locally

From the repo root you can run services directly (useful for debugging):

```bash
# Run the scheduler for testing (requires ffmpeg installed locally)
cd capture_service
python scheduler.py

# Run the UI service
cd ui_service
python main.py
```

> Note: When running locally you may want to set `IMAGE_DIR`/`TIMELAPSE_DIR` to local paths and ensure permissions exist.

---

## Troubleshooting

- Check container logs for errors (ffmpeg failures, permission issues):
  `docker-compose logs -f capture_service`
- Ensure `ffmpeg` is installed in the `capture_service` image and accessible in PATH.
- Ensure `shared_volume` is mounted and writable by services.
- If the UI shows `Timelapse not found` or `Camera Image not found`, verify images exist in `/shared_volume/images/camera_<name>/`.
- Redis connectivity problems can be diagnosed via `docker-compose logs redis` and ensuring secrets/envs are correct.

---

## Project Structure

```
/ (repo root)
├─ capture_service/        # scheduler, scripts, Dockerfile
├─ ui_service/             # FastAPI app, Dockerfile
├─ opencast/               # small client to talk to Opencast server
├─ utils/                  # shared settings and helpers
├─ shared_volume/          # images/ and timelapse/ (mounted by containers)
├─ docker-compose.yml
└─ README.md
```

---

## Contributing

Contributions are welcome — open issues or create a PR with changes. Keep changes small and documented.

### CI: Secret Scan (GitHub Actions)

This repository includes a GitHub Actions workflow that scans for accidental commits of secrets and sensitive files. The check runs on push and pull requests and will fail the job if:

- Any files are found in `secrets/` that are **not** named `*.example` or `.gitkeep`.
- Any files (excluding `*.example`, docs and images) contain suspicious secret-like keywords (e.g. `password`, `secret`, `api_key`, `BEGIN RSA PRIVATE`, `AKIA`, etc.).

To run the scan locally:

```bash
# make the script executable and run it
chmod +x .github/scripts/check-secrets.sh
.github/scripts/check-secrets.sh
```

If you need to store secrets for development, keep them out of the repository (use `.gitignore`, Docker secrets, or your secrets manager).

### Pre-commit hooks

This repository includes a recommended `.pre-commit-config.yaml` for local checks (formatting and basic repository hygiene).

Install and run pre-commit locally:

```bash
# Install pre-commit (Python/pip recommended) and ruff
pip install pre-commit ruff
# Install the git hooks
pre-commit install
# Run hooks against all files
pre-commit run --all-files
```

The config includes:
- trailing-whitespace, end-of-file-fixer, check-yaml, and check-added-large-files
- `ruff` for Python linting and formatting (`ruff-check` and `ruff-format`)

You can customize or extend `.pre-commit-config.yaml` as needed.

---

## License

This project is licensed under the Educational Community License, Version 2.0 (**ECL-2.0**). See the `LICENSE` file for details.

---

Happy monitoring! 🔭

```
>>>>>>> b0ea2c2 (Initial commit - adding project files)
