"""The fast front matter path must agree with the loader or step aside.

Every test here states the same contract from a different angle: for any input,
the fast reader and writer either produce exactly what the restricted YAML
implementation produces, or they decline. There is no third outcome, and no
input for which a difference is acceptable.
"""

from __future__ import annotations

import random
from typing import Any

import pytest
import yaml

from research_framework.storage.fast_yaml import dump_canonical, parse_canonical
from research_framework.storage.yaml_codec import (
    RestrictedDumper,
    RestrictedLoader,
    RestrictedYamlError,
    dump_restricted_yaml,
    load_restricted_yaml,
)


def reference_load(text: str) -> Any:
    return yaml.load(text, Loader=RestrictedLoader)


def reference_dump(value: Any) -> str:
    return yaml.dump(
        value,
        Dumper=RestrictedDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )


CANONICAL_SAMPLES = [
    "format_version: 1\nid: que-01J00000000000000000000001\nkind: question\n",
    "title: Larger contexts increase inference cost\nstatus: active\n",
    "tags:\n- cost\n- retrieval\naliases:\n- Q-main\n",
    "created_by:\n  kind: human\n  id: fedor\n",
    (
        "relations:\n- id: rel-01J0000000000000000000000R\n  kind: addresses\n"
        "  target: que-01J00000000000000000000001\n  created_by:\n    kind: agent\n"
        "    id: claude\n"
    ),
    "created_at: '2026-08-17T10:02:00+07:00'\n",
    "protocol_version: 1\nsize: 4096\nnegative: -17\n",
    "summary: null\nextensions: {}\nlimitations: []\n",
    "flag_true: true\nflag_false: false\n",
    "title: Улучшает ли изменение результат\n",
    "environment:\n  host: bench\n  cores: 12\n  nested:\n    deep: value\n",
    "quoted: 'yes'\nplain_yes: yes\nplain_no: no\nplain_on: on\n",
    "locator: https://example.invalid/paper/17\n",
    "outcome: completed\nverdict: supported\n",
]

# Shapes the fast path must refuse rather than interpret.
NON_CANONICAL_SAMPLES = [
    "anchor: &a value\nalias: *a\n",  # anchors and aliases
    "tagged: !!str 17\n",  # explicit tag
    "duplicate: 1\nduplicate: 2\n",  # duplicate key
    "? [complex, key]\n: value\n",  # complex key
    "commented: value # trailing comment\n",
    "# leading comment\nkey: value\n",
    "block: |\n  first line\n  second line\n",
    "folded: >\n  one long paragraph\n",
    "indented_sequence:\n  - one\n  - two\n",
    "flow_mapping: {a: 1, b: 2}\n",
    "flow_sequence: [1, 2, 3]\n",
    "hexadecimal: 0x1f\noctal: 0o17\n",
    "sexagesimal: 1:30\n",
    "floating: 1.5\nexponent: 1.0e+3\n",
    "underscored: 1_000\n",
    "merge_key: <<\nvalue_key: =\n",
    "timestamp_unquoted: 2026-08-17T10:02:00+07:00\n",
    "empty_value:\nnext: 1\n",
    'double_quoted: "needs \\"escapes\\""\n',
    "trailing_space: 'value '\n",
    "leading_dash: -value\n",
    "not_a_mapping\n",
    "- just\n- a\n- sequence\n",
    "",
]


@pytest.mark.contract
@pytest.mark.parametrize("text", CANONICAL_SAMPLES)
def test_fast_reader_matches_the_loader_on_canonical_front_matter(text: str) -> None:
    fast = parse_canonical(text)
    assert fast is not None, "canonical front matter must take the fast path"
    assert fast == reference_load(text)


@pytest.mark.contract
@pytest.mark.parametrize("text", NON_CANONICAL_SAMPLES)
def test_fast_reader_declines_anything_outside_the_subset(text: str) -> None:
    fast = parse_canonical(text)
    if fast is None:
        return
    # Declining is the expected answer, but agreeing is also correct as long as
    # the loader accepts the text and produces the very same value.
    assert fast == reference_load(text)


@pytest.mark.contract
@pytest.mark.parametrize("text", CANONICAL_SAMPLES)
def test_fast_writer_is_byte_identical_to_the_emitter(text: str) -> None:
    value = reference_load(text)
    fast = dump_canonical(value)
    assert fast is not None, "canonical values must take the fast path"
    assert fast == reference_dump(value)


@pytest.mark.contract
def test_declining_to_write_still_produces_emitter_output() -> None:
    # A folded long scalar and a multi-line string are outside the subset, so the
    # public function must fall through to PyYAML rather than fail.
    value = {
        "summary": "word " * 40,
        "rationale": "first line\nsecond line",
    }
    assert dump_canonical(value) is None
    assert dump_restricted_yaml(value) == reference_dump(value)


@pytest.mark.contract
def test_public_reader_still_reports_restricted_yaml_violations() -> None:
    for text in ("anchor: &a 1\nuse: *a\n", "duplicate: 1\nduplicate: 2\n"):
        with pytest.raises(RestrictedYamlError):
            load_restricted_yaml(text)


def _random_scalar(rng: random.Random) -> Any:
    choice = rng.randrange(9)
    if choice == 0:
        return rng.randrange(-10_000, 10_000)
    if choice == 1:
        return rng.choice([True, False])
    if choice == 2:
        return None
    if choice == 3:
        return ""
    if choice == 4:
        return rng.choice(["yes", "no", "on", "off", "null", "true", "~", "1.5"])
    if choice == 5:
        return "2026-08-17T10:02:00+07:00"
    if choice == 6:
        return rng.choice(["Улучшение", "naïve", "日本語", "a — b"])
    if choice == 7:
        return rng.choice(
            ["value: with colon", "trailing ", " leading", "hash # inside", "-dash"]
        )
    # Lengths chosen to straddle the emitter's 100-column fold, which is the one
    # place where a writer that looks right on short values silently diverges.
    return " ".join(["word"] * rng.randrange(1, 6)) + "x" * rng.randrange(70, 120)


def _random_value(rng: random.Random, depth: int = 0) -> Any:
    if depth >= 2 or rng.random() < 0.5:
        return _random_scalar(rng)
    if rng.random() < 0.5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(0, 4))]
    return {
        f"key_{index}": _random_value(rng, depth + 1)
        for index in range(rng.randrange(0, 4))
    }


@pytest.mark.contract
def test_writer_and_reader_agree_with_pyyaml_over_random_documents() -> None:
    rng = random.Random(20260908)
    accepted_write = accepted_read = 0
    for _ in range(2000):
        value = {
            f"field_{index}": _random_value(rng) for index in range(rng.randrange(1, 6))
        }
        expected_text = reference_dump(value)
        fast_text = dump_canonical(value)
        if fast_text is not None:
            accepted_write += 1
            assert fast_text == expected_text

        fast_value = parse_canonical(expected_text)
        if fast_value is not None:
            accepted_read += 1
            assert fast_value == reference_load(expected_text)

        # Whichever path is taken, the public functions must round-trip.
        assert load_restricted_yaml(dump_restricted_yaml(value)) == value

    # A fast path that never triggers would pass every assertion above while
    # delivering none of the point of having one.
    assert accepted_write > 100
    assert accepted_read > 100
