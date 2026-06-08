"""Built-in Skill: Screenshot Analyze — multimodal UI screenshot analysis.

Design decisions:
- Accepts image input as local file path or base64 string.
- OpenCV preprocessing: resize, optional edge detection, base64 encoding.
- Calls Qwen-VL (阿里云百炼) for structured UI analysis.
- MD5-based result caching to avoid redundant API calls.
- Returns structured JSON: components, layout, colors, typography.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from kiracode.skills.registry import SkillMeta

logger = logging.getLogger(__name__)

skill_meta = SkillMeta(
    name="screenshot_analyze",
    description="Analyze UI screenshots with vision AI to extract components, layout, and style info",
    tags=["screenshot", "vision", "ui", "multimodal", "design", "截图", "界面", "视觉"],
    capabilities=["screenshot_analyze", "ui_analysis", "visual_design"],
    source="builtin",
)

# ── Result cache (module-level, keyed by image MD5) ────────────────────────
_result_cache: dict[str, dict[str, Any]] = {}
_CACHE_MAX_SIZE = 64


def _compute_image_md5(image_bytes: bytes) -> str:
    return hashlib.md5(image_bytes).hexdigest()


def _get_cached_result(md5_hash: str) -> dict[str, Any] | None:
    return _result_cache.get(md5_hash)


def _set_cached_result(md5_hash: str, result: dict[str, Any]) -> None:
    if len(_result_cache) >= _CACHE_MAX_SIZE:
        oldest_key = next(iter(_result_cache))
        del _result_cache[oldest_key]
    _result_cache[md5_hash] = result


# ── OpenCV preprocessing ───────────────────────────────────────────────────

def _preprocess_image(
    image_bytes: bytes,
    detail_level: str = "standard",
) -> bytes:
    """Preprocess image with OpenCV: resize, optional edge detection.

    Args:
        image_bytes: Raw image bytes.
        detail_level: "fast" | "standard" | "detailed".

    Returns:
        Processed image bytes (JPEG encoded).
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.warning("OpenCV not installed, skipping preprocessing")
        return image_bytes

    # Decode
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        logger.warning("Failed to decode image, returning raw bytes")
        return image_bytes

    # Resize to fit within 1024x1024 (preserve aspect ratio)
    h, w = img.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Detail-level specific processing
    if detail_level == "detailed":
        # Light denoising
        img = cv2.fastNlMeansDenoisingColored(img, None, 6, 6, 7, 21)
    elif detail_level == "standard":
        # Gentle Gaussian blur for noise reduction
        img = cv2.GaussianBlur(img, (3, 3), 0)

    # "fast" mode: skip extra processing, just resize

    # Encode to JPEG (smaller than PNG for API transmission)
    _, buffer = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buffer.tobytes()


def _load_image_input(image_input: str) -> tuple[bytes, str]:
    """Load image from file path or base64 string.

    Returns:
        (image_bytes, mime_type)
    """
    # Case 1: base64 data URI
    if image_input.startswith("data:image/"):
        match = re.match(r"data:(image/\w+);base64,(.+)", image_input, re.DOTALL)
        if not match:
            raise ValueError(f"Invalid base64 data URI format")
        mime_type = match.group(1)
        raw = match.group(2)
        return base64.b64decode(raw), mime_type

    # Case 2: raw base64 string (no prefix)
    # Heuristic: base64 strings are long, only contain A-Za-z0-9+/=, and
    # don't look like file paths (no drive letter, no extension).
    if len(image_input) > 50 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", image_input):
        try:
            decoded = base64.b64decode(image_input.strip())
            if len(decoded) < 8:
                raise ValueError("Too short")
            # Check magic bytes
            if decoded[:8] == b"\x89PNG\r\n\x1a\n":
                return decoded, "image/png"
            if decoded[:2] == b"\xff\xd8":
                return decoded, "image/jpeg"
            if decoded[:4] == b"RIFF" and decoded[8:12] == b"WEBP":
                return decoded, "image/webp"
            return decoded, "image/png"
        except Exception:
            pass

    # Case 3: file path
    path = Path(image_input)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_input}")
    suffix = path.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".bmp": "image/bmp"}
    mime_type = mime_map.get(suffix, "image/png")
    return path.read_bytes(), mime_type


# ── Qwen-VL API (阿里云百炼) ──────────────────────────────────────────────

ANALYSIS_PROMPT = """你是一个专业的 UI/UX 分析专家。请仔细分析这张 UI 截图，并以严格的 JSON 格式返回分析结果。

要求：
1. 识别所有可见的 UI 组件（按钮、输入框、卡片、导航栏、图片、文本、图标、分割线等）
2. 分析整体布局结构
3. 提取配色方案
4. 分析排版风格

请严格按以下 JSON Schema 输出，不要添加任何额外文本：

{
  "components": [
    {
      "type": "button|input|card|navbar|image|text|icon|divider|header|footer|sidebar|modal|dropdown|checkbox|radio|toggle|avatar|badge|tag|list|table|form",
      "text": "组件内的文字内容（如适用）",
      "position": {"x": 0, "y": 0, "width": 100, "height": 50},
      "color": {"bg": "#ffffff", "text": "#000000", "border": "#cccccc"},
      "style": "组件的视觉风格描述",
      "confidence": 0.95
    }
  ],
  "layout": {
    "type": "flex|grid|absolute|stack",
    "direction": "vertical|horizontal|mixed",
    "description": "整体布局结构的文字描述",
    "sections": ["header", "main", "sidebar", "footer"]
  },
  "colors": {
    "primary": "#007bff",
    "secondary": "#6c757d",
    "background": "#ffffff",
    "surface": "#f8f9fa",
    "text_primary": "#212529",
    "text_secondary": "#6c757d",
    "accent": "#28a745",
    "palette": ["#007bff", "#ffffff", "#212529"]
  },
  "typography": {
    "font_family": "sans-serif",
    "heading_style": "bold, large",
    "body_style": "regular, medium",
    "font_sizes": {"heading": "24px", "body": "14px", "caption": "12px"}
  },
  "style_suggestions": "基于分析结果给出的前端实现建议（如推荐使用 Tailwind CSS、Flexbox 布局等）",
  "tech_recommendations": {
    "framework": "react|vue|html",
    "styling": "tailwind|css-modules|styled-components|bootstrap",
    "layout_strategy": "flexbox|grid|mixed"
  }
}"""

_FAST_PROMPT = """分析这张 UI 截图，返回 JSON 格式的结果：
{
  "components": [{"type": "组件类型", "text": "文字内容", "position": {"x": 0, "y": 0, "width": 100, "height": 50}}],
  "layout": {"type": "布局类型", "description": "布局描述"},
  "colors": {"primary": "#颜色", "background": "#颜色", "palette": ["颜色列表"]},
  "style_suggestions": "前端实现建议"
}"""


async def _call_qwen_vl(
    image_base64: str,
    mime_type: str,
    detail_level: str,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, Any]:
    """Call Qwen-VL API via OpenAI-compatible endpoint."""
    import httpx

    prompt = ANALYSIS_PROMPT if detail_level != "fast" else _FAST_PROMPT
    data_uri = f"data:{mime_type};base64,{image_base64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    return _parse_vl_response(content)


def _parse_vl_response(content: str) -> dict[str, Any]:
    """Parse Qwen-VL response, extracting JSON from potential markdown fences."""
    # Try to extract JSON from markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_match:
        content = json_match.group(1).strip()

    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        brace_match = re.search(r"\{.*\}", content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

    # Fallback: return raw text as structured wrapper
    return {
        "components": [],
        "layout": {"type": "unknown", "description": content[:500]},
        "colors": {},
        "style_suggestions": content[:500],
        "raw_response": content,
        "parse_error": True,
    }


# ── Skill Class ────────────────────────────────────────────────────────────


class SkillClass:
    """Screenshot analysis skill using Qwen-VL vision model."""

    def __init__(self) -> None:
        self._api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        self._base_url = os.environ.get(
            "QWEN_VL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self._model = os.environ.get("QWEN_VL_MODEL", "qwen-vl-max")
        self._yolo_detector = None

    def _get_yolo_detector(self) -> Any:
        """Lazy-load YOLO UI detector if available."""
        if self._yolo_detector is None:
            try:
                from kiracode.models.ui_detector import UIDetector
                self._yolo_detector = UIDetector()
            except (ImportError, Exception) as e:
                logger.info("YOLO UI detector not available: %s", e)
                self._yolo_detector = False
        return self._yolo_detector if self._yolo_detector is not False else None

    async def execute(
        self,
        image_input: str,
        detail_level: str = "standard",
        enable_yolo: bool = False,
    ) -> dict[str, Any]:
        """Analyze a UI screenshot and return structured description.

        Args:
            image_input: File path or base64 data URI.
            detail_level: "fast" | "standard" | "detailed".
            enable_yolo: Whether to run YOLO UI element detection first.

        Returns:
            Structured analysis: {components, layout, colors, typography, ...}
        """
        if not self._api_key:
            return {
                "success": False,
                "error": "DASHSCOPE_API_KEY not set. Export it or add to config.",
            }

        # 1. Load image
        try:
            image_bytes, mime_type = _load_image_input(image_input)
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}

        # 2. Check cache
        img_md5 = _compute_image_md5(image_bytes)
        cache_key = f"{img_md5}:{detail_level}"
        cached = _get_cached_result(cache_key)
        if cached is not None:
            logger.info("Cache hit for image %s", img_md5[:8])
            return {"success": True, **cached, "cached": True}

        # 3. OpenCV preprocessing
        processed_bytes = await asyncio.to_thread(
            _preprocess_image, image_bytes, detail_level
        )
        image_b64 = base64.b64encode(processed_bytes).decode("utf-8")

        # 4. Optional YOLO detection
        yolo_results = None
        if enable_yolo:
            detector = self._get_yolo_detector()
            if detector:
                try:
                    yolo_results = await detector.detect(image_bytes)
                except Exception as e:
                    logger.warning("YOLO detection failed: %s", e)

        # 5. Call Qwen-VL
        try:
            analysis = await _call_qwen_vl(
                image_base64=image_b64,
                mime_type="image/jpeg",
                detail_level=detail_level,
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
            )
        except Exception as e:
            return {"success": False, "error": f"Qwen-VL API call failed: {e}"}

        # 6. Merge YOLO results if available
        if yolo_results and not analysis.get("parse_error"):
            analysis["yolo_detections"] = yolo_results.get("detections", [])
            # Enrich component positions with YOLO bboxes if available
            _merge_yolo_into_analysis(analysis, yolo_results)

        # 7. Cache and return
        _set_cached_result(cache_key, analysis)
        return {
            "success": True,
            "cached": False,
            "image_md5": img_md5,
            "detail_level": detail_level,
            "model": self._model,
            **analysis,
        }


def _merge_yolo_into_analysis(
    analysis: dict[str, Any], yolo_results: dict[str, Any]
) -> None:
    """Merge YOLO detection bboxes into the component list for higher precision."""
    yolo_detections = yolo_results.get("detections", [])
    if not yolo_detections:
        return

    components = analysis.get("components", [])
    for det in yolo_detections:
        # Check if a similar component already exists by position overlap
        matched = False
        for comp in components:
            comp_pos = comp.get("position", {})
            det_box = det.get("bbox", {})
            if _positions_overlap(comp_pos, det_box, threshold=0.3):
                # Enrich existing component with YOLO confidence
                comp["yolo_confidence"] = det.get("confidence", 0)
                comp["yolo_class"] = det.get("class", "")
                matched = True
                break
        if not matched:
            # Add as new component from YOLO
            components.append({
                "type": det.get("class", "unknown"),
                "text": "",
                "position": {
                    "x": det.get("bbox", {}).get("x1", 0),
                    "y": det.get("bbox", {}).get("y1", 0),
                    "width": det.get("bbox", {}).get("x2", 0) - det.get("bbox", {}).get("x1", 0),
                    "height": det.get("bbox", {}).get("y2", 0) - det.get("bbox", {}).get("y1", 0),
                },
                "yolo_confidence": det.get("confidence", 0),
                "yolo_class": det.get("class", ""),
                "source": "yolo",
            })
    analysis["components"] = components


def _positions_overlap(pos_a: dict, box_b: dict, threshold: float = 0.3) -> bool:
    """Check if two bounding boxes overlap by more than threshold (IoU approximation)."""
    ax1, ay1 = pos_a.get("x", 0), pos_a.get("y", 0)
    ax2, ay2 = ax1 + pos_a.get("width", 0), ay1 + pos_a.get("height", 0)
    bx1, by1 = box_b.get("x1", 0), box_b.get("y1", 0)
    bx2, by2 = box_b.get("x2", 0), box_b.get("y2", 0)

    # Intersection
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix1 >= ix2 or iy1 >= iy2:
        return False

    intersection = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - intersection

    return (intersection / union) > threshold
