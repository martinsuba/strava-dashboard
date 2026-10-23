"""Loading segments.yaml and slugs (REQ-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdash.segments import SegmentError, load_segments, slugify


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("River path north", "river-path-north"),
        ("Ünïcode & Co: sprint!", "unicode-co-sprint"),
        ("  Hill   Road -- climb ", "hill-road-climb"),
        ("Climb 2", "climb-2"),
    ],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_slugify_without_letters_is_an_error() -> None:
    with pytest.raises(SegmentError, match="slug"):
        slugify("!!!")


def _yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "segments.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_segments_slug_is_independent_of_order(tmp_path: Path) -> None:
    body = (
        '- name: "River path north"\n  ref_activity: 1000000001\n'
        "  start: [-47.0, -134.0]\n  end: [-46.98, -134.0]\n"
    )
    other = body.replace("River path north", "Other one")
    (a,) = load_segments(_yaml(tmp_path, body))
    both = load_segments(_yaml(tmp_path, other + body))
    assert a.slug == "river-path-north" == both[1].slug
    assert a.ref_activity == "1000000001"  # ints become strings
    assert a.start == (-47.0, -134.0) and a.end == (-46.98, -134.0)


def test_missing_segments_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match=r"segments\.yaml"):
        load_segments(tmp_path / "segments.yaml")


def test_missing_field_names_segment_and_field(tmp_path: Path) -> None:
    p = _yaml(tmp_path, '- name: "Broken"\n  ref_activity: "1"\n  start: [-47.0, -134.0]\n')
    with pytest.raises(SegmentError, match=r"Broken.*end"):
        load_segments(p)
