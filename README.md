# 🎬 EfStrGenerator - AI Subtitle (SRT) Generator
**EfStrGenerator** is a desktop application that generates high-accuracy **SRT subtitles** from video and audio files using [CrisperWhisper](https://github.com/nyrahealth/CrisperWhisper) AI transcription.
On **Linux**, the app runs the full transcription pipeline locally. On **Windows**, where CrisperWhisper is not natively supported, the app acts as a client that delegates transcription to a Docker-based backend (FastAPI + GPU Worker + RabbitMQ).

---
## ✨ Features
- **Multi-format input** — supports `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`, `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a` and more.
- **Multi-language detection** — English, French, Spanish, German, Italian, Portuguese, Japanese, Chinese, Russian, Arabic, Hindi, Korean, Turkish, Polish, Ukrainian, Vietnamese, Indonesian, and Auto-Detect.
- **Verbatim & Intended modes** — `verbatim` captures stutters, fillers, and exact speech events; `intended` produces clean, readable text.
- **CUDA acceleration** — uses GPU when available for faster transcription.

---
## 🚀 Quick Start
### Prerequisites
#### Linux
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/) (`sudo apt install ffmpeg` or equivalent)
- NVIDIA GPU + CUDA drivers (recommended, falls back to CPU)
#### Windows
- Python 3.9+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL 2 backend
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU support inside Docker)
- ~8 GB disk space for the PyTorch CUDA Docker image
---
### Running from Source
#### 1. Clone the Repository
```bash
git clone https://github.com/your-username/EfStrGenerator.git
cd EfStrGenerator
```
#### 2. Set up a Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```
#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```
#### 4. Launch
```bash
python main.py
```
> On Windows, the app automatically starts the Docker backend on launch. Just make sure Docker Desktop is running.
---
### Standalone Binaries
Download pre-packaged releases from the [Releases Page](https://github.com/your-username/EfStrGenerator/releases):
- **Windows**: `EfStrGenerator-Windows-x64.zip` — requires Docker Desktop running in the background.
- **Linux**: `EfStrGenerator-x86_64.AppImage` — standalone, no Docker needed.
- **macOS**: `EfStrGenerator-macOS.zip`
---
## 📦 Building Executables Locally
These steps build the **desktop client** only. On Windows, the Docker backend is still required at runtime.
```bash
pip install pyinstaller
python build_app.py
```
The resulting executable will be created inside the `dist/` directory.
### CI/CD
The GitHub Actions workflow `.github/workflows/build.yml` automatically builds binaries for Windows, Linux, and macOS on pushes to `main` or version tags (e.g. `v1.0.0`).
---
## 📂 Project Structure
```
EfStrGenerator/
├── main.py              # Entry point: desktop GUI
├── api.py               # Entry point: FastAPI server
├── worker.py            # Entry point: RabbitMQ consumer
├── build_app.py         # PyInstaller packaging script
├── requirements.txt     # Linux desktop app dependencies
├── Dockerfile.api       # Lightweight API container (python:3.11-slim)
├── Dockerfile.worker    # GPU worker container (PyTorch + CUDA)
├── docker-compose.yml
└── src/
    ├── constants.py         # LANGUAGE_MAPPING
    ├── audio.py             # Audio extraction via FFmpeg
    ├── audio_splitter.py    # Silence-based audio chunking
    ├── srt_formatter.py     # SRT timestamp formatting and block builder
    ├── transcriber.py       # Local transcription pipeline (Linux)
    ├── api_client.py        # All FastAPI HTTP calls (shared by GUI + worker)
    ├── backend.py           # Docker Compose init (Windows)
    ├── gui.py               # Desktop GUI (Linux: full pipeline, Windows: REST client)
    ├── watchdog.py          # Docker teardown watchdog (Windows)
    ├── database.py          # SQLAlchemy ORM models + session
    ├── schemas.py           # Pydantic request/response schemas
    ├── queue.py             # RabbitMQ publisher
    ├── routes.py            # FastAPI route handlers
    ├── transcription.py     # Worker transcription pipeline (Docker)
    └── worker_consumer.py   # RabbitMQ consumer loop
```
---
## 📄 License
Distributed under the MIT License. See `LICENSE` for details.
