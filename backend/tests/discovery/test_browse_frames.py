"""FrameStore — path safety, and the housekeeping AvatarStore deliberately lacks."""

import io
import time

import pytest
from PIL import Image

from app.discovery.media.shots import PUBLIC_PREFIX, FrameStore


def _jpeg(width: int = 1600, height: int = 900) -> bytes:
    image = Image.new("RGB", (width, height), (10, 14, 28))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


@pytest.fixture()
def store(tmp_path) -> FrameStore:
    return FrameStore(tmp_path / "frames", max_edge=512, ttl_seconds=60, max_files=4)


def test_a_saved_frame_is_served_from_its_public_path(store):
    path = store.save("sess-1", 3, _jpeg())

    assert path == f"{PUBLIC_PREFIX}/sess-1/3.jpg", f"got {path!r}"
    assert store.resolve("sess-1", "3.jpg") is not None, "the frame just written did not resolve"


def test_a_frame_is_downscaled_to_the_configured_long_edge(store):
    store.save("sess-1", 1, _jpeg(1600, 900))
    resolved = store.resolve("sess-1", "1.jpg")

    with Image.open(resolved) as image:
        assert max(image.size) <= 512, f"frame kept at {image.size}"


@pytest.mark.parametrize(
    "session_id,name",
    [
        ("../../etc", "1.jpg"),
        ("sess-1", "../../../secrets.env"),
        ("sess-1", "1.jpg.exe"),
        ("sess-1", "index.html"),
        ("sess/1", "1.jpg"),
        ("", "1.jpg"),
        ("sess-1", ""),
    ],
)
def test_traversal_and_bogus_names_never_resolve(store, session_id, name):
    store.save("sess-1", 1, _jpeg())

    assert store.resolve(session_id, name) is None, f"{session_id!r}/{name!r} resolved to a file"


def test_a_frame_that_was_never_written_resolves_to_nothing(store):
    assert store.resolve("sess-1", "9.jpg") is None


def test_an_unsafe_session_id_is_refused_at_write_time(store):
    assert store.save("../escape", 1, _jpeg()) == "", "a traversing session id was written"


def test_empty_data_is_not_written(store):
    assert store.save("sess-1", 1, b"") == "", "an empty frame was written"


def test_purge_removes_one_sessions_frames_and_leaves_the_others(store):
    for step in range(3):
        store.save("sess-1", step, _jpeg())
    store.save("sess-2", 0, _jpeg())

    removed = store.purge("sess-1")

    assert removed == 3, f"got {removed}"
    assert store.resolve("sess-1", "0.jpg") is None, "a purged frame still resolves"
    assert store.resolve("sess-2", "0.jpg") is not None, "purge crossed into another session"


def test_sweep_drops_frames_past_the_ttl_and_keeps_fresh_ones(store):
    store.save("old", 0, _jpeg())
    store.save("new", 0, _jpeg())
    stale = store.resolve("old", "0.jpg")
    ancient = time.time() - 3600
    import os

    os.utime(stale, (ancient, ancient))

    removed = store.sweep()

    assert removed == 1, f"got {removed}"
    assert store.resolve("old", "0.jpg") is None, "a stale frame survived the sweep"
    assert store.resolve("new", "0.jpg") is not None, "a fresh frame was swept"


def test_sweep_enforces_the_file_cap_oldest_first(store):
    import os

    # All comfortably inside the TTL, so this test measures the cap alone —
    # stamping them into the past would let the TTL branch remove everything
    # and the cap would never be exercised.
    now = time.time()
    for step in range(7):
        store.save("sess", step, _jpeg())
        target = store.resolve("sess", f"{step}.jpg")
        stamp = now - 30 + step
        os.utime(target, (stamp, stamp))

    removed = store.sweep()

    assert removed == 3, f"expected to fall back to the cap of 4, removed {removed}"
    assert store.resolve("sess", "0.jpg") is None, "the oldest frame survived"
    assert store.resolve("sess", "6.jpg") is not None, "the newest frame was removed"


def test_sweeping_an_empty_store_is_harmless(tmp_path):
    assert FrameStore(tmp_path / "nothing").sweep() == 0
