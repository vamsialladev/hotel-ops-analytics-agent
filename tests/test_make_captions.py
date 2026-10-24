"""scripts/make_captions.py: caption timing and file formats (pure functions; no model, no ffmpeg)."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("make_captions", ROOT / "scripts" / "make_captions.py")
mc = importlib.util.module_from_spec(spec)
sys.modules["make_captions"] = mc  # dataclasses look their module up while the class is created
spec.loader.exec_module(mc)


def test_timestamps():
    assert mc.timestamp(0) == "00:00:00,000"
    assert mc.timestamp(75.25) == "00:01:15,250"
    assert mc.timestamp(3725.5, ".") == "01:02:05.500"
    assert mc.timestamp(-1) == "00:00:00,000"


def test_short_segment_is_one_cue():
    cues = mc.split_segment(1.0, 3.0, "  I built this   because staff wait. ")
    assert cues == [mc.Cue(1.0, 3.0, "I built this because staff wait.")]


def test_long_segment_splits_into_two_line_cues_within_its_time():
    text = "This is for front-desk staff at a hotel. " * 6
    cues = mc.split_segment(10.0, 22.0, text)
    assert len(cues) > 1
    assert cues[0].start == 10.0 and cues[-1].end <= 22.0
    assert all(c.end > c.start for c in cues)
    assert all(len(line) <= mc.LINE_CHARS for c in cues for line in c.text.split("\n"))
    assert all(c.text.count("\n") < mc.MAX_LINES for c in cues)
    assert all(c.end - c.start <= mc.MAX_CUE_SECONDS + 0.01 for c in cues)


def test_empty_segment_has_no_cue():
    assert mc.split_segment(0, 1, "   ") == []


def test_srt_and_vtt():
    segs = [SimpleNamespace(start=0.4, end=2.0, text=" Hello."), SimpleNamespace(start=2.5, end=4.0, text="Next.")]
    cues = mc.cues_from_segments(segs)
    srt, vtt = mc.to_srt(cues), mc.to_vtt(cues)
    assert srt.startswith("1\n00:00:00,400 --> 00:00:02,000\nHello.\n\n2\n00:00:02,500")
    assert vtt.startswith("WEBVTT\n\n00:00:00.400 --> 00:00:02.000\nHello.\n")


def test_newest_video_skips_captioned_copies(tmp_path):
    import os

    (tmp_path / "a.mp4").write_bytes(b"")
    (tmp_path / "b.mp4").write_bytes(b"")
    (tmp_path / "b-captioned.mp4").write_bytes(b"")
    os.utime(tmp_path / "a.mp4", (1, 1))
    assert mc.newest_video(tmp_path).name == "b.mp4"
    assert mc.newest_video(tmp_path / "missing") is None


def test_srt_round_trip_after_a_hand_correction():
    cues = [mc.Cue(0.4, 2.0, "Hello from Mountain Lodge."), mc.Cue(2.5, 4.25, "Two\nlines.")]
    assert mc.parse_srt(mc.to_srt(cues)) == cues
    assert mc.parse_srt(mc.to_srt(cues).replace("\n", "\r\n")) == cues  # edited in Notepad
    assert mc.parse_srt("garbage\n\n") == []
