"""Legacy single-shot capture seam kept for older experiments.

The live browser-first demo path runs through the session-based station backend in
`service.py`, `session_runtime.py`, and `oak4_engine.py`. New capture work should not
extend this module unless that older flow is intentionally revived.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import depthai as dai
except ImportError:  # pragma: no cover - hardware dependency
    dai = None

from .models import StartCaptureSessionRequest as CaptureRequest


class DepthAIUnavailableError(RuntimeError):
    """Raised when the device-side capture path cannot be used."""


@dataclass(slots=True)
class CameraArtifact:
    content: bytes
    extension: str
    media_type: str
    captured_at: datetime
    metadata: dict[str, Any]


class DepthAIClient:
    """Legacy client retained for compatibility, not for the live session API path."""

    def __init__(self, *, simulate: bool, oak_device_id: str | None) -> None:
        self.simulate = simulate
        self.oak_device_id = oak_device_id

    def capture(self, capture_id: str, request: CaptureRequest) -> CameraArtifact:
        should_simulate = request.simulate if request.simulate is not None else self.simulate
        if should_simulate:
            return self._simulate_capture(capture_id, request)
        return self._capture_with_device(capture_id, request)

    def _simulate_capture(self, capture_id: str, request: CaptureRequest) -> CameraArtifact:
        captured_at = datetime.now(timezone.utc)
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#0f2d21" />
      <stop offset="100%" stop-color="#b58d3d" />
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#bg)" rx="24" />
  <text x="60" y="110" fill="#f7f2e8" font-size="52" font-family="monospace">OAKProof Simulated Capture</text>
  <text x="60" y="190" fill="#f7f2e8" font-size="30" font-family="monospace">capture_id: {capture_id}</text>
  <text x="60" y="240" fill="#f7f2e8" font-size="30" font-family="monospace">asset_id: {request.asset_id}</text>
  <text x="60" y="290" fill="#f7f2e8" font-size="30" font-family="monospace">captured_at: {captured_at.isoformat()}</text>
  <text x="60" y="340" fill="#f7f2e8" font-size="30" font-family="monospace">operator_id: {request.operator_id or "unassigned"}</text>
  <text x="60" y="390" fill="#f7f2e8" font-size="28" font-family="monospace">legacy capture seam: not used by the live session API</text>
</svg>"""
        return CameraArtifact(
            content=svg.encode("utf-8"),
            extension=".svg",
            media_type="image/svg+xml",
            captured_at=captured_at,
            metadata={
                "mode": "simulate",
                "oak_device_id": self.oak_device_id,
                "requested_tags": request.tags,
            },
        )

    def _capture_with_device(self, capture_id: str, request: CaptureRequest) -> CameraArtifact:
        if dai is None:
            raise DepthAIUnavailableError(
                "DepthAI is not installed in this environment. Install dependencies or enable CAPTURE_SIMULATE."
            )

        available_devices = dai.Device.getAllAvailableDevices()
        if not available_devices:
            raise DepthAIUnavailableError(
                "No OAK device detected. Attach the OAK4 station or set CAPTURE_SIMULATE=true."
            )

        raise DepthAIUnavailableError(
            "Legacy DepthAIClient device capture is not implemented. Use the session-based capture service "
            f"for capture_id {capture_id} / asset {request.asset_id}."
        )
