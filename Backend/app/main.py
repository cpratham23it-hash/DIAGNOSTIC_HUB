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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import connect_to_mongo, close_mongo_connection
from app.routers import auth, diagnoses, faults, files, symptoms, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts
    connect_to_mongo()
    yield
    # Runs once when the server shuts down
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