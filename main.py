from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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
app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")
