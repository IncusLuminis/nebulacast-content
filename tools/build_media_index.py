#!/usr/bin/env python3
"""Build the static catalog consumed by media/index.html."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


MEDIA_EXTENSIONS = {
    ".webm": "video",
    ".mp4": "video",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
}

# Cloudflare Pages rejects an individual static asset above 25 MiB.
PAGES_MAX_FILE_SIZE = 25 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--media-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "media",
        help="Cloudflare Pages publish root",
    )
    parser.add_argument(
        "--validate-pages",
        action="store_true",
        help="Fail if an asset exceeds the Cloudflare Pages per-file limit",
    )
    return parser.parse_args()


def human_title(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def build_catalog(media_dir: Path, validate_pages: bool) -> dict[str, object]:
    media_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, object]] = []
    oversized: list[tuple[str, int]] = []

    for path in sorted(media_dir.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue

        extension = path.suffix.lower()
        media_type = MEDIA_EXTENSIONS.get(extension)
        if media_type is None:
            continue

        relative_path = path.relative_to(media_dir).as_posix()
        stat = path.stat()
        if stat.st_size > PAGES_MAX_FILE_SIZE:
            oversized.append((relative_path, stat.st_size))

        assets.append(
            {
                "path": relative_path,
                "name": path.name,
                "title": human_title(path),
                "type": media_type,
                "format": extension.removeprefix("."),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime,
                    tz=timezone.utc,
                ).isoformat(timespec="seconds"),
            }
        )

    if validate_pages and oversized:
        details = "\n".join(
            f"  - {path}: {size / 1024 / 1024:.1f} MiB"
            for path, size in oversized
        )
        raise SystemExit(
            "Cloudflare Pages accepts static files up to 25 MiB. "
            f"These files are too large:\n{details}"
        )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(assets),
        "assets": assets,
    }


def main() -> None:
    args = parse_args()
    media_dir = args.media_dir.resolve()
    catalog = build_catalog(media_dir, args.validate_pages)
    output = media_dir / "library.json"
    output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Indexed {catalog['count']} assets: {output}")


if __name__ == "__main__":
    main()
