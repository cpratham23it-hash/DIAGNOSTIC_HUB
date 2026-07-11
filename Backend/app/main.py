"""
Diagnos backend entry point.

Run locally with:
    uvicorn app.main:app --reload --port 8000

Routers are added here as they're built in later steps:
  - system     (Step 1, this file)
  - auth       (Steps 3-5)
  - files      (Module 0 — generic upload/download)
  - diagnoses  (Module 2b — input collection)
  - faults     (Module 2a — fault reference database)
  - symptoms   (Module 1 — guided symptom checker)
  - appliances, technicians, etc. (later modules)
"""

from contextlib import asynccontextmanager

import os
# Ensure ffmpeg is on PATH so librosa/audioread can decode WebM recordings
_FFMPEG_BIN = r"C:\Users\Pratham\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin"
if os.path.isdir(_FFMPEG_BIN):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_to_mongo, close_mongo_connection
from app.routers import auth, diagnoses, faults, files, symptoms, system, appliances


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm: suppress TF noise and load models before first request
    import os
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    connect_to_mongo()
    try:
        from app.ml.inference import get_classifier, model_is_available
        if model_is_available("fridge"):
            get_classifier("fridge")
            print("[startup] Fan model loaded.")
        if model_is_available("washer"):
            get_classifier("washer")
            print("[startup] Washer model loaded.")
    except Exception as e:
        print(f"[startup] ML pre-warm skipped: {e}")
    yield
    close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(files.router)
app.include_router(diagnoses.router)
app.include_router(faults.router)
app.include_router(symptoms.router)
app.include_router(appliances.router)