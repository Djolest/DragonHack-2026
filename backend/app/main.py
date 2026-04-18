from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import AnchorResult, ReceiptRecord, SignedReceiptEnvelope, VerificationResult
from .repository import ReceiptRepository
from .services.flare_anchor import FlareAnchorService
from .services.receipts import ReceiptService

settings = get_settings()
repository = ReceiptRepository(settings.storage_root)
receipt_service = ReceiptService(settings, repository)
anchor_service = FlareAnchorService(settings)

app = FastAPI(title=settings.app_name, version="0.1.0")
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
        "storedReceipts": repository.count(),
        "anchoringEnabled": anchor_service.is_enabled(),
    }


@app.post("/api/v1/receipts", response_model=ReceiptRecord, status_code=status.HTTP_202_ACCEPTED)
async def ingest_receipt(receipt: SignedReceiptEnvelope) -> ReceiptRecord:
    try:
        return receipt_service.ingest(receipt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/receipts/{receipt_id}", response_model=ReceiptRecord)
async def get_receipt(receipt_id: str) -> ReceiptRecord:
    try:
        return receipt_service.get_or_raise(receipt_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/receipts/{receipt_id}/anchor", response_model=AnchorResult)
async def anchor_receipt(receipt_id: str) -> AnchorResult:
    try:
        record = receipt_service.get_or_raise(receipt_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        anchor_result = anchor_service.anchor(record)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    receipt_service.mark_anchored(receipt_id, anchor_result)
    return anchor_result


@app.get("/api/v1/receipts/{receipt_id}/verify", response_model=VerificationResult)
async def verify_receipt(receipt_id: str) -> VerificationResult:
    try:
        return receipt_service.build_verification(receipt_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
