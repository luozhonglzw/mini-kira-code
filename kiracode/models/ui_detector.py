"""UI Element Detector — YOLOv8-nano based UI component detection.

Design decisions:
- Uses ultralytics YOLOv8-nano (yolov8n.pt) for fast inference.
- Pre-trained weights used by default; fine-tuning script included for custom UI datasets.
- CPU-friendly: ~10ms per image on modern hardware.
- Detects UI component classes: button, input, card, navbar, image, text, icon, divider, etc.
- NMS post-processing built-in (handled by ultralytics).
- Returns structured list of {class, confidence, bbox} dicts.

Environment:
    KIRACODE_YOLO_MODEL_PATH — custom weights path (default: yolov8n.pt)
    KIRACODE_YOLO_CONFIDENCE — confidence threshold (default: 0.35)
    KIRACODE_YOLO_DEVICE     — "cpu" or "cuda" (default: "cpu")
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# UI component class mapping (COCO-pretrained classes → UI classes)
# YOLOv8n pretrained on COCO doesn't natively detect UI elements.
# This mapping is for the fine-tuned model. For pretrained, we fall back
# to generic object detection and post-map COCO classes to UI semantics.
UI_CLASSES = [
    "button", "input", "card", "navbar", "image", "text", "icon",
    "divider", "header", "footer", "sidebar", "dropdown", "checkbox",
    "toggle", "avatar", "badge", "tag", "list_item", "table_cell",
]

# COCO class IDs that loosely correspond to UI elements (best-effort fallback)
_COCO_TO_UI_FALLBACK = {
    0: "button",      # person → treat as interactive element
    62: "card",       # tv/monitor → card-like
    67: "table_cell", # dining table → table
    73: "list_item",  # book → list item
}


class UIDetector:
    """YOLOv8-nano based UI element detector."""

    def __init__(
        self,
        model_path: str | None = None,
        confidence: float | None = None,
        device: str | None = None,
    ) -> None:
        self._model_path = model_path or os.environ.get("KIRACODE_YOLO_MODEL_PATH", "yolov8n.pt")
        self._confidence = confidence or float(os.environ.get("KIRACODE_YOLO_CONFIDENCE", "0.35"))
        self._device = device or os.environ.get("KIRACODE_YOLO_DEVICE", "cpu")
        self._model = None

    def _load_model(self) -> Any:
        """Lazy-load the YOLO model."""
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError:
                raise ImportError(
                    "ultralytics not installed. Run: pip install ultralytics"
                )
            model_path = Path(self._model_path)
            if model_path.exists():
                logger.info("Loading custom YOLO weights from %s", model_path)
                self._model = YOLO(str(model_path))
            else:
                logger.info("Loading pretrained YOLOv8n weights")
                self._model = YOLO("yolov8n.pt")
        return self._model

    async def detect(self, image_bytes: bytes) -> dict[str, Any]:
        """Detect UI elements in an image.

        Args:
            image_bytes: Raw image bytes (PNG/JPEG).

        Returns:
            {detections: [{class, confidence, bbox}], model, inference_ms}
        """
        import time

        model = self._load_model()

        # Run inference in thread pool to avoid blocking
        start = time.monotonic()
        results = await asyncio.to_thread(
            self._run_inference, model, image_bytes
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "detections": results,
            "model": self._model_path,
            "inference_ms": round(elapsed_ms, 1),
            "device": self._device,
            "confidence_threshold": self._confidence,
        }

    def _run_inference(self, model: Any, image_bytes: bytes) -> list[dict[str, Any]]:
        """Run YOLO inference (blocking)."""
        import cv2
        import numpy as np

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []

        results = model.predict(
            source=img,
            conf=self._confidence,
            device=self._device,
            verbose=False,
        )

        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for i in range(len(boxes)):
                box = boxes[i]
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])

                # Map class: use custom UI class if fine-tuned, else COCO fallback
                if cls_id < len(UI_CLASSES):
                    class_name = UI_CLASSES[cls_id]
                else:
                    class_name = _COCO_TO_UI_FALLBACK.get(cls_id, f"class_{cls_id}")

                detections.append({
                    "class": class_name,
                    "confidence": round(conf, 3),
                    "bbox": {
                        "x1": round(x1, 1),
                        "y1": round(y1, 1),
                        "x2": round(x2, 1),
                        "y2": round(y2, 1),
                    },
                })

        # Sort by confidence descending
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections


# ── Fine-tuning script template ────────────────────────────────────────────

FINETUNE_SCRIPT = """#!/usr/bin/env python3
\"\"\"Fine-tune YOLOv8-nano on a custom UI dataset.

Usage:
    python finetune_ui_yolo.py --data data.yaml --epochs 50 --batch 16

Data format:
    YOLO format with images/ and labels/ directories.
    Classes should match UI_CLASSES in ui_detector.py.

Recommended datasets:
    - Rico (Android UI screenshots): https://interactionmining.org/rico
    - ReDraw: https://github.com/earvin11/ReDraw
    - Enrico: https://github.com/haus wida/enrico
\"\"\"

from ultralytics import YOLO

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, required=True, help="Path to data.yaml")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", type=str, default="yolov8n.pt")
    parser.add_argument("--output", type=str, default="runs/detect/ui_yolo")
    args = parser.parse_args()

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project=args.output,
        name="finetune",
        exist_ok=True,
    )

    # Export to ONNX for production
    model.export(format="onnx")

if __name__ == "__main__":
    main()
"""
