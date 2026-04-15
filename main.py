from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.builder import router as builder_router

app = FastAPI(
    title="AI Scheduler — Builder API",
    description="Generates labeled training payloads for the AI Scheduler",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(builder_router)


@app.get("/")
def root():
    return {"message": "Builder API is running", "version": "1.0.0"}
