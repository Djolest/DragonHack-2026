from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import get_settings
from .models import CaptureRequest, CaptureResponse
from .service import CaptureService

settings = get_settings()
service = CaptureService(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "simulate": settings.simulate,
        "stationId": settings.station_id,
    }


@app.post("/api/v1/capture", response_model=CaptureResponse)
async def capture_endpoint(request: CaptureRequest) -> CaptureResponse:
    try:
        return await service.capture(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/assets/{asset_path:path}")
async def get_asset(asset_path: str) -> FileResponse:
    try:
        file_path = service.storage.resolve_asset_path(asset_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found.")

    return FileResponse(file_path)
