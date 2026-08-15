from __future__ import annotations

from pathlib import Path
from typing import Iterable, Literal
import shutil
import subprocess
import tempfile
import numpy as np
import imageio.v2 as imageio


OutputFormat = Literal["webm", "gif", "mp4"]


def normalize_output_format(fmt: str) -> OutputFormat:
    fmt = fmt.lower().strip()

    if fmt not in {"webm", "gif", "mp4"}:
        raise ValueError("output_format must be one of: webm, gif, mp4")

    return fmt  # type: ignore[return-value]


def ensure_out_dir(path: str | Path) -> Path:
    out_dir = Path(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found. Install it first:\n"
            "  macOS: brew install ffmpeg\n"
            "  conda: conda install -c conda-forge ffmpeg"
        )


def _frames_to_temp_pngs(
    frames: Iterable[np.ndarray],
    frame_dir: Path,
    *,
    on_frame=None,
) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)

    for i, frame in enumerate(frames):
        imageio.imwrite(frame_dir / f"frame_{i:04d}.png", frame)
        if on_frame is not None:
            on_frame(i + 1)


def _export_webm_ffmpeg(
    frame_dir: Path,
    out_file: Path,
    fps: int,
    crf: int = 32,
    quiet: bool = False,
) -> None:
    require_ffmpeg()

    cmd = [
        "ffmpeg", "-y",
        *(["-v", "error"] if quiet else []),
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libvpx-vp9",
        "-b:v", "0",
        "-crf", str(crf),
        "-pix_fmt", "yuva420p",
        "-auto-alt-ref", "0",
        "-metadata:s:v:0", "alpha_mode=1",
        "-row-mt", "1",
        str(out_file),
    ]

    subprocess.run(cmd, check=True)


def flatten_rgba_frames(
    frames: list[np.ndarray],
    background: tuple[int, int, int] = (3, 11, 16),
) -> list[np.ndarray]:
    """Composite RGBA frames onto an opaque plate for H.264/MP4 export."""
    flat: list[np.ndarray] = []
    bg = np.array(background, dtype=np.uint8)
    for frame in frames:
        arr = np.asarray(frame, dtype=np.uint8)
        if arr.ndim != 3:
            flat.append(arr)
            continue
        if arr.shape[2] == 3:
            flat.append(arr)
            continue
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
        out = rgb * alpha + bg.astype(np.float32) * (1.0 - alpha)
        flat.append(np.clip(out, 0, 255).astype(np.uint8))
    return flat


def _export_mp4_ffmpeg(
    frame_dir: Path,
    out_file: Path,
    fps: int,
    crf: int = 20,
    quiet: bool = False,
) -> None:
    require_ffmpeg()

    # H.264/yuv420p requires even width and height (e.g. 441x777 fails).
    cmd = [
        "ffmpeg", "-y",
        *(["-v", "error"] if quiet else []),
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-vf", "pad=width=ceil(iw/2)*2:height=ceil(ih/2)*2:x=0:y=0:color=black@0.0",
        "-c:v", "libx264",
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_file),
    ]

    subprocess.run(cmd, check=True)


def _export_gif_imageio(
    frames: list[np.ndarray],
    out_file: Path,
    fps: int,
) -> None:
    imageio.mimsave(
        out_file,
        frames,
        fps=fps,
        loop=0,
    )


def export_animation(
    frames: list[np.ndarray],
    out_dir: str | Path,
    animation_name: str,
    output_format: str,
    fps: int,
    cleanup_frames: bool = True,
    webm_crf: int = 32,
    mp4_crf: int = 20,
    verbose: bool = True,
    log_fn=print,
) -> Path:
    """
    Export animation frames to webm/gif/mp4.

    Expected frame format:
      - list[np.ndarray]
      - RGB uint8 frames: shape (H, W, 3)
      - RGBA uint8 frames also accepted: shape (H, W, 4)

    Output:
      animations/<animation_name>/<animation_name>.<format>
    """

    fmt = normalize_output_format(output_format)

    if not frames:
        raise ValueError("frames list is empty")

    out_dir = ensure_out_dir(out_dir)
    out_file = out_dir / f"{animation_name}.{fmt}"

    def _say(message: str = "") -> None:
        if verbose:
            log_fn(message, flush=True)

    if fmt == "mp4":
        frames = flatten_rgba_frames(frames)

    if fmt == "gif":
        _say(f"→ Writing GIF ({len(frames)} frames @ {fps} fps)…")
        _export_gif_imageio(frames, out_file, fps)
        _say(f"✓ GIF saved: {out_file}")
        return out_file

    frame_dir = Path(tempfile.mkdtemp(prefix=".frames-export-", dir=out_dir))

    total = len(frames)

    # NOTE (nebulacast local copy): the upstream per-frame "\r"-updating progress
    # bar assumes a real terminal that collapses carriage returns in place. In a
    # notebook/Binder context each print becomes its own output line instead, so
    # a 100+ frame export turns into 100+ lines. Dropped the per-frame callback;
    # the single "start"/"done" _say() lines below are enough signal here.
    try:
        _say(f"→ Writing {total} PNG frame(s) to temp folder…")
        _frames_to_temp_pngs(frames, frame_dir)

        if fmt == "webm":
            _say(f"→ ffmpeg VP9/WebM (crf={webm_crf})…")
            _export_webm_ffmpeg(
                frame_dir=frame_dir,
                out_file=out_file,
                fps=fps,
                crf=webm_crf,
                quiet=True,  # always suppress ffmpeg's own chatter; use verbose for our own _say() lines
            )

        elif fmt == "mp4":
            _say(f"→ ffmpeg H.264/MP4 (crf={mp4_crf})…")
            _export_mp4_ffmpeg(
                frame_dir=frame_dir,
                out_file=out_file,
                fps=fps,
                crf=mp4_crf,
                quiet=True,  # always suppress ffmpeg's own chatter; use verbose for our own _say() lines
            )

    finally:
        if cleanup_frames:
            shutil.rmtree(frame_dir, ignore_errors=True)
            if verbose:
                _say("  temp PNG folder removed")

    _say(f"✓ {fmt.upper()} saved: {out_file}")
    return out_file


def preview_output_path(source_file: Path) -> Path:
    source_file = Path(source_file)
    return source_file.with_name(f"{source_file.stem}_pr.webm")


def export_webm_preview(
    source_file: str | Path,
    *,
    out_file: str | Path | None = None,
    width: int = 216,
    height: int = 160,
    fps: int = 12,
    crf: int = 40,
    verbose: bool = True,
    log_fn=print,
) -> Path:
    """Small VP9/WebM preview from a rendered WebM (216×160 by default)."""
    require_ffmpeg()

    source_file = Path(source_file).resolve()
    if not source_file.is_file():
        raise FileNotFoundError(f"Source video not found: {source_file}")

    out_path = Path(out_file).resolve() if out_file else preview_output_path(source_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    target_w = max(2, int(width))
    target_h = max(2, int(height))
    target_fps = max(1, int(fps))
    vf = (
        f"fps={target_fps},"
        f"scale={target_w}:{target_h}:flags=lanczos,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=0x00000000"
    )

    if verbose:
        log_fn(
            f"→ Preview WebM ({target_w}×{target_h}, {target_fps} fps) → {out_path}",
            flush=True,
        )

    cmd = [
        "ffmpeg", "-y",
        *(["-v", "error"] if not verbose else []),
        "-i", str(source_file),
        "-vf", vf,
        "-an",
        "-c:v", "libvpx-vp9",
        "-b:v", "0",
        "-crf", str(max(0, int(crf))),
        "-pix_fmt", "yuva420p",
        "-auto-alt-ref", "0",
        "-metadata:s:v:0", "alpha_mode=1",
        "-row-mt", "1",
        str(out_path),
    ]

    subprocess.run(cmd, check=True)

    if verbose:
        size_kb = out_path.stat().st_size / 1024
        log_fn(f"✓ Preview saved: {out_path} ({size_kb:.1f} KB)", flush=True)

    return out_path
