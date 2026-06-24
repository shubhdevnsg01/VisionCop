from visioncop.core import detect_media_type
from visioncop.utils import format_timestamp, merge_timestamps


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00.000"
    assert format_timestamp(65.4321) == "00:01:05.432"
    assert format_timestamp(3661.001) == "01:01:01.001"


def test_merge_timestamps():
    assert merge_timestamps([], 1.0) == []
    assert merge_timestamps([0, 0.5, 3, 3.2], 1.0) == [(0, 0.5), (3, 3.2)]


def test_detect_media_type():
    assert detect_media_type(__import__("pathlib").Path("clip.mp4")) == "video"
    assert detect_media_type(__import__("pathlib").Path("face.jpg")) == "image"
