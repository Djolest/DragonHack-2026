from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .models import CaptureSessionStatus, StartCaptureSessionRequest, StopCaptureSessionResponse
from .service import CaptureService


def create_app(
    settings: Settings | None = None,
    service: CaptureService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_service = service or CaptureService(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        resolved_settings.storage_root.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": resolved_settings.app_name,
            "environment": resolved_settings.app_env,
            "simulate": resolved_settings.simulate,
        }

    @app.post("/api/v1/capture/sessions", response_model=CaptureSessionStatus)
    async def start_capture_session(request: StartCaptureSessionRequest) -> CaptureSessionStatus:
        try:
            return resolved_service.start_session(request)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/capture/sessions/{session_id}", response_model=CaptureSessionStatus)
    async def get_capture_session(session_id: str) -> CaptureSessionStatus:
        try:
            return resolved_service.get_session_status(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Capture session not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/v1/capture/sessions/{session_id}/stop",
        response_model=StopCaptureSessionResponse,
    )
    async def stop_capture_session(session_id: str) -> StopCaptureSessionResponse:
        try:
            return StopCaptureSessionResponse(session=resolved_service.stop_session(session_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Capture session not found.") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/assets/{asset_path:path}")
    async def get_asset(asset_path: str) -> FileResponse:
        try:
            file_path = resolved_service.storage.resolve_asset_path(asset_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Asset not found.")
        return FileResponse(file_path)

    return app


settings = get_settings()
service = CaptureService(settings)
app = create_app(settings=settings, service=service)
