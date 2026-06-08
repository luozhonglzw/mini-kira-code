"""Test script for KiraCode screenshot analysis (OpenCV + Qwen-VL)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Auto-load .env
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Check API key
api_key = os.environ.get("DASHSCOPE_API_KEY", "")
if not api_key:
    print("[ERROR] DASHSCOPE_API_KEY not set!")
    print("  Set it in .env file or export it.")
    sys.exit(1)
print(f"[OK] DASHSCOPE_API_KEY loaded ({api_key[:8]}...{api_key[-4:]})")

# Check image path
image_path = sys.argv[1] if len(sys.argv) > 1 else "tests/screenshots/demo.png"
image_path = str(Path(__file__).resolve().parent / "screenshots" / "demo.png")
if not Path(image_path).exists():
    print(f"[ERROR] Image not found: {image_path}")
    sys.exit(1)
print(f"[OK] Image found: {image_path} ({Path(image_path).stat().st_size} bytes)")


async def main():
    from kiracode.skills.builtin.screenshot_analyze import SkillClass

    skill = SkillClass()
    print(f"[OK] Skill loaded, model={skill._model}, base_url={skill._base_url}")
    print()
    print("=" * 60)
    print("  Calling Qwen-VL API (detail_level=standard)...")
    print("=" * 60)
    print()

    result = await skill.execute(
        image_input=image_path,
        detail_level="standard",
        enable_yolo=False,
    )

    if not result.get("success"):
        print(f"[FAIL] {result.get('error', 'unknown error')}")
        return

    print("[OK] Analysis complete!")
    print()

    # Pretty print results
    print("=" * 60)
    print("  COMPONENTS")
    print("=" * 60)
    components = result.get("components", [])
    print(f"  Found {len(components)} component(s):")
    for i, c in enumerate(components[:10], 1):
        ctype = c.get("type", "?")
        text = c.get("text", "")[:40]
        conf = c.get("confidence", 0)
        print(f"  {i}. {ctype:12s}  confidence={conf:.2f}  text=\"{text}\"")

    print()
    print("=" * 60)
    print("  LAYOUT")
    print("=" * 60)
    layout = result.get("layout", {})
    print(f"  Type:        {layout.get('type', '?')}")
    print(f"  Direction:   {layout.get('direction', '?')}")
    print(f"  Description: {layout.get('description', '?')[:100]}")
    print(f"  Sections:    {layout.get('sections', [])}")

    print()
    print("=" * 60)
    print("  COLORS")
    print("=" * 60)
    colors = result.get("colors", {})
    for key in ("primary", "secondary", "background", "surface", "text_primary", "accent"):
        val = colors.get(key)
        if val:
            print(f"  {key:15s}: {val}")
    palette = colors.get("palette", [])
    if palette:
        print(f"  palette:       {palette[:8]}")

    print()
    print("=" * 60)
    print("  TYPOGRAPHY")
    print("=" * 60)
    typo = result.get("typography", {})
    if typo:
        print(f"  Font family:   {typo.get('font_family', '?')}")
        print(f"  Heading style: {typo.get('heading_style', '?')}")
        print(f"  Body style:    {typo.get('body_style', '?')}")
        print(f"  Font sizes:    {typo.get('font_sizes', {})}")
    else:
        print("  (not available)")

    print()
    print("=" * 60)
    print("  TECH RECOMMENDATIONS")
    print("=" * 60)
    tech = result.get("tech_recommendations", {})
    if tech:
        print(f"  Framework:  {tech.get('framework', '?')}")
        print(f"  Styling:    {tech.get('styling', '?')}")
        print(f"  Layout:     {tech.get('layout_strategy', '?')}")
    else:
        print("  (not available)")

    suggestions = result.get("style_suggestions", "")
    if suggestions:
        print()
        print("=" * 60)
        print("  STYLE SUGGESTIONS")
        print("=" * 60)
        print(f"  {suggestions[:300]}")

    print()
    print("=" * 60)
    print("  METADATA")
    print("=" * 60)
    print(f"  Success:      {result.get('success')}")
    print(f"  Cached:       {result.get('cached')}")
    print(f"  Image MD5:    {result.get('image_md5', '?')[:16]}...")
    print(f"  Detail level: {result.get('detail_level')}")
    print(f"  Model:        {result.get('model')}")

    # Save full JSON
    json_path = Path(image_path).parent / "analysis_result.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print()
    print(f"  Full JSON saved to: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
