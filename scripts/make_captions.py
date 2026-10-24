"""Captions from my own voice: transcribe a recorded demo with faster-whisper (local, free) and burn them in.

    python scripts/make_captions.py                        # newest .mp4 in docs/video/
    python scripts/make_captions.py docs/video/demo.mp4    # a specific file
    python scripts/make_captions.py --no-burn              # only write the .srt and .vtt
    python scripts/make_captions.py --model small.en       # a larger model if names come out wrong
    python scripts/make_captions.py --burn-only            # after fixing names in the .srt by hand

Writes next to the video: <name>.srt, <name>.vtt and <name>-captioned.mp4 (captions burned in, audio copied).
Runs offline after the first run (the model is downloaded once from Hugging Face into the local cache).
Needs ffmpeg on PATH and `pip install faster-whisper` (dev only). No AI voice: this only transcribes mine.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "docs" / "video"
LINE_CHARS = 42  # characters per caption line (a common subtitle limit)
MAX_LINES = 2
MAX_CUE_SECONDS = 6.0
STYLE = "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=4,MarginV=28"


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def timestamp(seconds: float, sep: str = ",") -> str:
    """SRT uses 00:00:01,250; WebVTT uses 00:00:01.250."""
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def split_segment(start: float, end: float, text: str) -> list[Cue]:
    """One transcribed segment -> cues of at most two lines and MAX_CUE_SECONDS, timed by text length."""
    text = " ".join(text.split())
    if not text:
        return []
    chunk = LINE_CHARS * MAX_LINES
    pieces = textwrap.wrap(text, chunk, break_long_words=False) or [text]
    total = sum(len(p) for p in pieces)
    cues, t = [], start
    for piece in pieces:
        span = (end - start) * len(piece) / total
        cue_end = min(t + max(span, 0.8), end) if t + 0.8 <= end else end
        cues.append(Cue(round(t, 3), round(cue_end, 3), "\n".join(textwrap.wrap(piece, LINE_CHARS))))
        t = cue_end
    out = []
    for cue in cues:  # very long cues are split in time, keeping the same text lines
        if cue.end - cue.start > MAX_CUE_SECONDS and "\n" in cue.text:
            mid = round((cue.start + cue.end) / 2, 3)
            first, second = cue.text.split("\n", 1)
            out += [Cue(cue.start, mid, first), Cue(mid, cue.end, second)]
        else:
            out.append(cue)
    return out


def cues_from_segments(segments) -> list[Cue]:
    """faster-whisper segments (anything with .start, .end, .text) -> caption cues in order."""
    cues = []
    for seg in segments:
        cues += split_segment(float(seg.start), float(seg.end), seg.text)
    return cues


def to_srt(cues: list[Cue]) -> str:
    return "".join(f"{i}\n{timestamp(c.start)} --> {timestamp(c.end)}\n{c.text}\n\n" for i, c in enumerate(cues, 1))


def parse_srt(text: str) -> list[Cue]:
    """Read an .srt back (after I've corrected it by hand)."""
    cues = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = block.strip().split("\n")
        if len(lines) < 3 or " --> " not in lines[1]:
            continue
        start, end = (seconds(t.strip()) for t in lines[1].split(" --> "))
        cues.append(Cue(start, end, "\n".join(lines[2:])))
    return cues


def seconds(stamp: str) -> float:
    hms, ms = stamp.replace(".", ",").split(",")
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s + int(ms) / 1000


def to_vtt(cues: list[Cue]) -> str:
    body = "".join(f"{timestamp(c.start, '.')} --> {timestamp(c.end, '.')}\n{c.text}\n\n" for c in cues)
    return "WEBVTT\n\n" + body


def newest_video(folder: Path = VIDEO_DIR) -> Path | None:
    videos = [p for p in folder.glob("*.mp4") if not p.stem.endswith("-captioned")]
    return max(videos, key=lambda p: p.stat().st_mtime) if videos else None


def ffmpeg(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True, cwd=cwd)


def extract_audio(video: Path, wav: Path) -> None:
    ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav))


def read_wav(wav: Path):
    """16 kHz mono 16-bit WAV (from extract_audio) -> float32 samples. Read here rather than by faster-whisper,
    whose PyAV decoder breaks when PyAV and faster-whisper versions drift apart."""
    import wave

    import numpy as np  # installed with faster-whisper

    with wave.open(str(wav), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav: Path, model: str, language: str):
    from faster_whisper import WhisperModel  # dev-only dependency

    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _ = whisper.transcribe(read_wav(wav), language=language, vad_filter=True, beam_size=5)
    return list(segments)


def burn(video: Path, srt: Path, out: Path) -> None:
    """Burn the captions in. Runs inside the video's folder so the subtitles filter gets a plain file name
    (Windows drive letters and backslashes break its argument parsing)."""
    ffmpeg(
        *("-i", video.name, "-vf", f"subtitles={srt.name}:force_style='{STYLE}'"),
        *("-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "copy", "-movflags", "+faststart"),
        out.name,
        cwd=video.parent,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("video", nargs="?", type=Path, help="default: the newest .mp4 in docs/video/")
    parser.add_argument("--model", default="base.en", help="faster-whisper model (tiny.en, base.en, small.en ...)")
    parser.add_argument("--language", default="en")
    parser.add_argument("--no-burn", action="store_true", help="only write the .srt and .vtt")
    parser.add_argument("--burn-only", action="store_true", help="burn the existing (hand-corrected) .srt")
    args = parser.parse_args(argv)
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found. Install it (winget install Gyan.FFmpeg) and open a new terminal.")
        return 1
    video = (args.video or newest_video() or Path()).resolve()
    if not video.is_file():
        print("No video found. Put your recording in docs/video/ (MP4) or pass its path.")
        return 1
    srt, vtt = video.with_suffix(".srt"), video.with_suffix(".vtt")
    if args.burn_only:
        if not srt.is_file():
            print(f"{srt.name} not found: run without --burn-only first.")
            return 1
        vtt.write_text(to_vtt(parse_srt(srt.read_text(encoding="utf-8"))), encoding="utf-8")
        out = video.with_name(video.stem + "-captioned.mp4")
        burn(video, srt, out)
        print(f"wrote {out.name} and {vtt.name} from your corrected {srt.name}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        extract_audio(video, wav)
        cues = cues_from_segments(transcribe(wav, args.model, args.language))
    if not cues:
        print("No speech found in the audio track.")
        return 1
    srt.write_text(to_srt(cues), encoding="utf-8")
    vtt.write_text(to_vtt(cues), encoding="utf-8")
    print(f"wrote {srt.name} and {vtt.name} ({len(cues)} captions). Read them once and fix any names by hand.")
    if not args.no_burn:
        out = video.with_name(video.stem + "-captioned.mp4")
        burn(video, srt, out)
        print(f"wrote {out.name} (captions burned in, your audio unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
