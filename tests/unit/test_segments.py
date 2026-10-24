"""Loading segments.yaml and slugs (REQ-003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdash.segments import (
    Segment,
    SegmentError,
    dump_segments,
    import_strava_csv,
    load_segments,
    load_segments_lenient,
    segment_from_entry,
    slugify,
    write_segments,
)


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


# --- T-006: validation, writing, segment add, import-strava ------------------------------------


def _entry(**over: object) -> str:
    fields: dict[str, object] = {
        "name": "Seg",
        "ref_activity": "1",
        "start": [-47.0, -134.0],
        "end": [-46.98, -134.0],
    }
    fields.update(over)
    return "- " + "\n  ".join(f"{k}: {json.dumps(v)}" for k, v in fields.items()) + "\n"


@pytest.mark.parametrize(
    ("over", "pattern"),
    [
        ({"start": [95.0, -134.0]}, r"Seg.*start latitude.*range"),
        ({"start": [-91.0, -134.0]}, r"Seg.*latitude.*range"),
        ({"end": [-47.0, 200.0]}, r"Seg.*end longitude.*range"),
        ({"end": [-47.0, -181.0]}, r"Seg.*longitude.*range"),
        ({"start": ["x", -134.0]}, r"Seg.*start.*numeric"),
        ({"start": [True, 1.0]}, r"Seg.*start.*numeric"),
        ({"start": [1.0]}, r"Seg.*start.*lat, lon"),
        ({"start": "-47,-134"}, r"Seg.*start.*lat, lon"),
        ({"end": None}, r"Seg.*end"),
        ({"ref_activity": "../../x"}, r"Seg.*ref_activity.*activity ID"),
        ({"ref_activity": "12a"}, r"Seg.*ref_activity"),
        ({"ref_activity": True}, r"Seg.*ref_activity"),
        ({"ref_activity": 1.5}, r"Seg.*ref_activity"),
        ({"name": ""}, r"segment #1.*name"),
        ({"name": 12}, r"segment #1.*name"),
        ({"colour": "red"}, r"Seg.*unknown field colour"),
    ],
)
def test_invalid_entry_names_segment_and_problem(
    tmp_path: Path, over: dict[str, object], pattern: str
) -> None:
    with pytest.raises(SegmentError, match=pattern):
        load_segments(_yaml(tmp_path, _entry(**over)))


@pytest.mark.parametrize("field", ["name", "ref_activity", "start", "end"])
def test_missing_each_field(tmp_path: Path, field: str) -> None:
    lines = _entry().splitlines()
    text = "\n".join(line for line in lines if not line.strip(" -").startswith(field + ":")) + "\n"
    if field == "name":
        text = text.replace("  ref_activity", "- ref_activity", 1)
    with pytest.raises(SegmentError, match=rf"missing field {field}"):
        load_segments(_yaml(tmp_path, text))


def test_not_a_list_or_mapping_and_bad_yaml(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match="list"):
        load_segments(_yaml(tmp_path, "a: 1\n"))
    with pytest.raises(SegmentError, match="segment #1"):
        load_segments(_yaml(tmp_path, "- just text\n"))
    with pytest.raises(SegmentError, match="invalid YAML"):
        load_segments(_yaml(tmp_path, "- [unclosed\n"))


def test_yaml_python_tags_are_not_executed(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match="invalid YAML"):
        load_segments(_yaml(tmp_path, "- !!python/object/apply:os.system ['true']\n"))


def test_duplicate_name_and_slug_collision(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match=r"Seg.*duplicate"):
        load_segments(_yaml(tmp_path, _entry() + _entry()))
    with pytest.raises(SegmentError, match=r"collides"):
        load_segments(_yaml(tmp_path, _entry(name="Hill-Climb") + _entry(name="hill climb")))


def test_empty_file_means_no_segments(tmp_path: Path) -> None:
    assert load_segments(_yaml(tmp_path, "")) == []
    assert load_segments(_yaml(tmp_path, "[]\n")) == []


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Přívoz", "privoz"),
        ("Žlutý kopec (nahoru)", "zluty-kopec-nahoru"),
        ("A/B  c.d", "a-b-c-d"),
        ("ČERVENÁ", "cervena"),
    ],
)
def test_slugify_accents_and_punctuation(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_dump_roundtrip_is_deterministic(tmp_path: Path) -> None:
    segs = [
        Segment('Přívoz: "quoted"', "privoz-quoted", "12", (-47.0, -134.5), (-46.9, -134.25)),
        Segment("B", "b", "13", (1.0, 2.0), (3.0, 4.0)),
    ]
    p = tmp_path / "segments.yaml"
    write_segments(p, segs)
    first = p.read_text(encoding="utf-8")
    assert load_segments(p) == segs
    write_segments(p, load_segments(p))
    assert p.read_text(encoding="utf-8") == first
    assert dump_segments([]) == "[]\n"


def test_write_is_atomic_and_keeps_old_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = _yaml(tmp_path, _entry())
    before = p.read_text()

    def boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("sdash.segments.os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        write_segments(p, [Segment("New", "new", "2", (0.0, 0.0), (1.0, 1.0))])
    assert p.read_text() == before
    assert [f.name for f in tmp_path.iterdir()] == ["segments.yaml"], "temp file left behind"


def test_write_refuses_duplicates_and_keeps_file(tmp_path: Path) -> None:
    p = _yaml(tmp_path, _entry())
    s = Segment("X", "x", "1", (0.0, 0.0), (1.0, 1.0))
    with pytest.raises(SegmentError, match="duplicate"):
        write_segments(p, [s, s])
    assert p.read_text() == _entry()


HEADER = "Segment Name,Activity ID,Starting Latitude,Starting Longitude,Ending Latitude,Ending Longitude\n"


def _csv(tmp_path: Path, *rows: str, header: str = HEADER) -> Path:
    p = tmp_path / "segments.csv"
    p.write_text(header + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def test_import_skips_existing_keeps_order_and_old_segments(tmp_path: Path) -> None:
    target = _yaml(tmp_path, _entry(name="Old"))
    csv_path = _csv(
        tmp_path,
        "Old,5,-47.0,-134.0,-46.9,-134.0",
        "New B,6,-47.0,-134.0,-46.9,-134.0",
        "New A,7,-47.1,-134.0,-46.9,-134.0",
        "New B,8,-47.0,-134.0,-46.9,-134.0",
    )
    report = import_strava_csv(csv_path, target)
    assert (report.added, report.skipped_existing, report.invalid) == (2, 2, [])
    segs = load_segments(target)
    assert [s.name for s in segs] == ["Old", "New B", "New A"]
    assert segs[0].ref_activity == "1" and segs[1].ref_activity == "6"


def test_import_creates_missing_file_and_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "segments.yaml"
    csv_path = _csv(tmp_path, "Přívoz,6,-47.0,-134.0,-46.9,-134.0")
    assert import_strava_csv(csv_path, target).added == 1
    assert import_strava_csv(csv_path, target).added == 0
    assert [s.slug for s in load_segments(target)] == ["privoz"]


def test_import_reports_invalid_rows_and_writes_only_valid(tmp_path: Path) -> None:
    target = _yaml(tmp_path, _entry(name="Old"))
    csv_path = _csv(
        tmp_path,
        "Good,6,-47.0,-134.0,-46.9,-134.0",
        "Bad lat,7,95.0,-134.0,-46.9,-134.0",
        "Bad num,8,x,-134.0,-46.9,-134.0",
        "Bad id,../1,-47.0,-134.0,-46.9,-134.0",
        ",9,-47.0,-134.0,-46.9,-134.0",
        "Short,9,-47.0",
        "good,10,-47.0,-134.0,-46.9,-134.0",
    )
    report = import_strava_csv(csv_path, target)
    assert report.added == 1
    assert [r for r, _ in report.invalid] == [3, 4, 5, 6, 7, 8]
    assert "Bad lat" in report.invalid[0][1] and "range" in report.invalid[0][1]
    assert "collides" in report.invalid[-1][1]
    assert [s.name for s in load_segments(target)] == ["Old", "Good"]


def test_import_nothing_new_leaves_file_untouched(tmp_path: Path) -> None:
    target = _yaml(tmp_path, "# my comment\n" + _entry(name="Old"))
    before = target.read_text()
    report = import_strava_csv(_csv(tmp_path, "Old,6,-47.0,-134.0,-46.9,-134.0"), target)
    assert report.added == 0 and target.read_text() == before


def test_import_bad_header_or_missing_csv(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match="missing column"):
        import_strava_csv(_csv(tmp_path, header="Name,Activity ID\n"), tmp_path / "s.yaml")
    with pytest.raises(SegmentError, match="not found"):
        import_strava_csv(tmp_path / "none.csv", tmp_path / "s.yaml")


def test_import_refuses_when_existing_file_is_invalid(tmp_path: Path) -> None:
    target = _yaml(tmp_path, _entry(start=[95.0, 0.0]))
    with pytest.raises(SegmentError, match="range"):
        import_strava_csv(_csv(tmp_path, "N,6,-47.0,-134.0,-46.9,-134.0"), target)


# --- T-006 fix round 1 -------------------------------------------------------------------------

BAD_CHARS = [
    chr(c) for c in (0x7F, 0x85, 0x9F, 0xFFFE, 0xFFFF, 0x00, 0x0A, 0x2028, 0x2029, 0xD800, 0xE000)
]


@pytest.mark.parametrize("ch", BAD_CHARS)
def test_names_with_control_or_invalid_characters_are_rejected(ch: str) -> None:
    entry = {"name": f"Del{ch}hill", "ref_activity": "1", "start": [0.0, 0.0], "end": [1.0, 1.0]}
    with pytest.raises(SegmentError, match=r"Del.*name contains"):
        segment_from_entry(entry)


def test_name_length_cap_and_empty_new_segment_message() -> None:
    entry: dict[str, object] = {
        "name": "x" * 121,
        "ref_activity": "1",
        "start": [0, 0],
        "end": [1, 1],
    }
    with pytest.raises(SegmentError, match="longer than 120"):
        segment_from_entry(entry)
    entry["name"] = "x" * 120
    segment_from_entry(entry)
    entry["name"] = ""
    with pytest.raises(SegmentError, match=r"new segment: name must be a non-empty"):
        segment_from_entry(entry)


def test_write_refuses_text_that_does_not_round_trip(tmp_path: Path) -> None:
    p = _yaml(tmp_path, _entry())
    before = p.read_text()
    bad = Segment("Del\x7fhill", "delhill", "1", (0.0, 0.0), (1.0, 1.0))
    with pytest.raises(SegmentError, match=r"read back|cannot be read"):
        write_segments(p, [bad])
    assert p.read_text() == before


def test_alias_bomb_in_ref_activity_fails_fast_with_short_message(tmp_path: Path) -> None:
    levels = ["a: &a0 [x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 9):
        levels.append(f"b{i}: &a{i} [" + ", ".join([f"*a{i - 1}"] * 9) + "]")
    anchors = "\n".join("    " + line for line in levels)
    text = (
        '- name: "Bomb"\n  ref_activity:\n' + anchors.replace("    a:", "    a:") + "\n"
        "  start: [0, 0]\n  end: [1, 1]\n"
    )
    # flow sequences nest ref_activity as a mapping of aliased lists (a type that is not int/str)
    with pytest.raises(SegmentError) as err:
        load_segments(_yaml(tmp_path, text))
    assert len(str(err.value)) < 300 and "Bomb" in str(err.value)


def test_long_strings_in_messages_are_capped(tmp_path: Path) -> None:
    with pytest.raises(SegmentError) as err:
        load_segments(_yaml(tmp_path, _entry(ref_activity="z" * 5000)))
    assert len(str(err.value)) < 300


def test_import_row_with_control_character_is_invalid_and_file_still_loads(tmp_path: Path) -> None:
    target = _yaml(tmp_path, _entry(name="Old"))
    csv_path = _csv(
        tmp_path, "Del\x7fhill,6,-47.0,-134.0,-46.9,-134.0", "Fine,7,-47.0,-134.0,-46.9,-134.0"
    )
    report = import_strava_csv(csv_path, target)
    assert report.added == 1 and [r for r, _ in report.invalid] == [2]
    assert [s.name for s in load_segments(target)] == ["Old", "Fine"]


# --- T-013: segment-level problems are collected, not fatal --------------------------------------


def _write_yaml(path: Path, *blocks: str) -> Path:
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return path


GOOD = '- name: "Good"\n  ref_activity: "1"\n  start: [-47.0, -134.0]\n  end: [-46.99, -134.0]'
NO_END = '- name: "No end"\n  ref_activity: "1"\n  start: [-47.0, -134.0]'
BAD_LAT = '- name: "Bad lat"\n  ref_activity: "1"\n  start: [95.0, -134.0]\n  end: [-46.9, -134.0]'
DUP = GOOD.replace("[-46.99, -134.0]", "[-46.5, -134.0]")


def test_lenient_load_keeps_valid_segments_and_reports_the_rest(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "segments.yaml", NO_END, GOOD, BAD_LAT)
    segments, problems = load_segments_lenient(path)
    assert [s.name for s in segments] == ["Good"]
    assert len(problems) == 2
    assert "No end" in problems[0] and "end" in problems[0]
    assert "Bad lat" in problems[1] and "range" in problems[1]


def test_lenient_load_keeps_the_first_of_duplicate_names(tmp_path: Path) -> None:
    path = _write_yaml(tmp_path / "segments.yaml", GOOD, DUP)
    segments, problems = load_segments_lenient(path)
    assert [s.name for s in segments] == ["Good"]
    assert segments[0].end == (-46.99, -134.0), "the first occurrence is kept"
    assert len(problems) == 1 and "Good" in problems[0] and "duplicate" in problems[0]


def test_lenient_load_skips_a_later_slug_collision(tmp_path: Path) -> None:
    other = GOOD.replace('"Good"', '"good!"')
    segments, problems = load_segments_lenient(_write_yaml(tmp_path / "s.yaml", GOOD, other))
    assert [s.name for s in segments] == ["Good"]
    assert len(problems) == 1 and "good!" in problems[0] and "slug" in problems[0]


def test_lenient_load_is_still_strict_about_the_file(tmp_path: Path) -> None:
    with pytest.raises(SegmentError, match="not found"):
        load_segments_lenient(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("- name: [unclosed\n")
    with pytest.raises(SegmentError, match="invalid YAML"):
        load_segments_lenient(bad)
    bad.write_text("name: not a list\n")
    with pytest.raises(SegmentError, match="list"):
        load_segments_lenient(bad)


def test_lenient_load_of_a_non_mapping_entry(tmp_path: Path) -> None:
    segments, problems = load_segments_lenient(_write_yaml(tmp_path / "s.yaml", "- 5", GOOD))
    assert [s.name for s in segments] == ["Good"]
    assert len(problems) == 1 and "#1" in problems[0]
