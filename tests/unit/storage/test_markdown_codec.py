from __future__ import annotations

from pathlib import Path

import pytest

from research_framework.storage.markdown_codec import MarkdownCodec, MarkdownCodecError
from tests.conftest import EXAMPLE_PROJECT, markdown_document, node_metadata


@pytest.fixture
def codec() -> MarkdownCodec:
    return MarkdownCodec()


@pytest.mark.contract
@pytest.mark.parametrize(
    "kind",
    [
        "question",
        "hypothesis",
        "claim",
        "experiment",
        "run",
        "evidence",
        "assessment",
        "source",
        "artifact",
        "decision",
    ],
)
def test_codec_reads_golden_example_of_every_node_kind(
    codec: MarkdownCodec, kind: str
) -> None:
    matches = list((EXAMPLE_PROJECT / "research" / f"{kind}s").glob("*.md"))
    if kind == "hypothesis":
        matches = list((EXAMPLE_PROJECT / "research" / "hypotheses").glob("*.md"))
    if kind == "evidence":
        matches = list((EXAMPLE_PROJECT / "research" / "evidence").glob("*.md"))
    assert matches, f"missing golden file for {kind}"

    document = codec.decode(matches[0].read_text(encoding="utf-8"), path=matches[0])

    assert document.metadata["kind"] == kind
    assert document.metadata["format_version"] == 1
    assert document.body.startswith("\n#")


@pytest.mark.contract
def test_codec_supports_human_friendly_yaml_features(codec: MarkdownCodec) -> None:
    text = """---
format_version: 1
id: hyp-01J00000000000000000000002
kind: hypothesis
title: "Context: 32k" # comments are allowed
status: active
statement: >-
  A larger context improves
  retrieval quality.
falsification_criteria: |
  Recall improves by less than 10%.
  The benchmark is fixed.
tags:
  - retrieval
  - context
created_at: 2026-08-17T10:00:00+07:00
created_by:
  kind: human
  id: fedor
updated_at: 2026-08-17T10:00:00+07:00
updated_by:
  kind: human
  id: fedor
relations: []
---

# Тело
"""

    document = codec.decode(text, path=Path("hypothesis.md"))

    assert document.metadata["title"] == "Context: 32k"
    assert document.metadata["statement"] == (
        "A larger context improves retrieval quality."
    )
    assert document.metadata["falsification_criteria"].endswith("\n")
    assert document.metadata["tags"] == ["retrieval", "context"]
    assert "# Тело" in document.body


@pytest.mark.contract
def test_yaml_12_boolean_like_words_remain_strings(codec: MarkdownCodec) -> None:
    metadata = node_metadata("question")
    text = markdown_document(metadata).replace('"title": "Test question"', "title: on")

    document = codec.decode(text, path=Path("question.md"))

    assert document.metadata["title"] == "on"


@pytest.mark.contract
def test_timestamps_remain_json_compatible_iso_strings(codec: MarkdownCodec) -> None:
    text = markdown_document(node_metadata("question"))

    document = codec.decode(text, path=Path("question.md"))

    assert document.metadata["created_at"] == "2026-08-17T10:00:00+07:00"
    assert isinstance(document.metadata["created_at"], str)


@pytest.mark.contract
def test_parse_encode_parse_preserves_semantic_metadata(codec: MarkdownCodec) -> None:
    source = markdown_document(
        node_metadata("hypothesis"),
        "# Heading\n\nParagraph with [[wiki-link]].\n",
    )

    first = codec.decode(source, path=Path("hypothesis.md"))
    encoded = codec.encode(first)
    second = codec.decode(encoded, path=Path("hypothesis.md"))

    assert second.metadata == first.metadata
    assert second.body == first.body


@pytest.mark.contract
def test_metadata_update_preserves_body_exactly(codec: MarkdownCodec) -> None:
    body = "\n# Heading\n\n- list\n- with trailing spaces  \n\n"
    source = markdown_document(node_metadata("hypothesis"), body)
    document = codec.decode(source, path=Path("hypothesis.md"))
    updated_metadata = dict(document.metadata)
    updated_metadata["summary"] = "New summary"

    encoded = codec.encode(document.with_metadata(updated_metadata))
    round_trip = codec.decode(encoded, path=Path("hypothesis.md"))

    assert round_trip.body == body
    assert round_trip.metadata["summary"] == "New summary"


@pytest.mark.contract
def test_encoder_uses_stable_top_level_field_order(codec: MarkdownCodec) -> None:
    metadata = node_metadata("question")
    metadata["summary"] = "Summary"
    metadata["tags"] = ["b", "a"]
    document = codec.decode(markdown_document(metadata), path=Path("question.md"))

    encoded = codec.encode(document)

    positions = [
        encoded.index(f"\n{field}:")
        for field in (
            "format_version",
            "id",
            "kind",
            "title",
            "status",
            "summary",
            "question",
            "tags",
            "created_at",
            "created_by",
            "updated_at",
            "updated_by",
            "relations",
        )
    ]
    assert positions == sorted(positions)
    assert encoded.index("- b") < encoded.index("- a")


@pytest.mark.contract
@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("# no front matter\n", "missing_front_matter"),
        ("---\nkind: question\n", "unclosed_front_matter"),
        ("---\n- kind\n- question\n---\n", "front_matter_not_mapping"),
        ("---\nkind: question\nkind: claim\n---\n", "duplicate_yaml_key"),
        ("---\ntitle: !!python/object:os.system {}\n---\n", "yaml_tag_forbidden"),
        ("---\ntitle: &shared value\nsummary: *shared\n---\n", "yaml_alias_forbidden"),
        (
            "---\ndefaults: &defaults\n  status: active\nnode:\n  <<: *defaults\n---\n",
            "yaml_alias_forbidden",
        ),
        ("---\n? [complex, key]\n: value\n---\n", "complex_yaml_key"),
        ("---\nvalue: !!set {a: null}\n---\n", "yaml_tag_forbidden"),
    ],
)
def test_restricted_yaml_rejects_ambiguous_or_unsafe_features(
    codec: MarkdownCodec, text: str, code: str
) -> None:
    with pytest.raises(MarkdownCodecError) as raised:
        codec.decode(text, path=Path("unsafe.md"))

    assert raised.value.code == code
    assert raised.value.path == Path("unsafe.md")


@pytest.mark.contract
def test_codec_never_executes_yaml_constructor(
    codec: MarkdownCodec, tmp_path: Path
) -> None:
    marker = tmp_path / "must-not-exist"
    payload = (
        f"---\nvalue: !!python/object/apply:pathlib.Path.touch ['{marker}']\n---\n"
    )

    with pytest.raises(MarkdownCodecError):
        codec.decode(payload, path=Path("payload.md"))

    assert not marker.exists()


@pytest.mark.contract
def test_git_conflict_markers_in_front_matter_have_specific_error(
    codec: MarkdownCodec,
) -> None:
    text = """---
format_version: 1
<<<<<<< HEAD
title: First
=======
title: Second
>>>>>>> branch
---
"""

    with pytest.raises(MarkdownCodecError) as raised:
        codec.decode(text, path=Path("conflicted.md"))

    assert raised.value.code == "git_conflict_marker"


@pytest.mark.contract
def test_front_matter_delimiter_inside_body_is_not_reparsed(
    codec: MarkdownCodec,
) -> None:
    body = "\n# Body\n\n---\n\nA thematic break.\n"
    text = markdown_document(node_metadata("question"), body)

    document = codec.decode(text, path=Path("question.md"))

    assert document.body == body
