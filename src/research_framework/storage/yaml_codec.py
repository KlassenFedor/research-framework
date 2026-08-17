from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

import yaml
from yaml.nodes import MappingNode, ScalarNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


class RestrictedYamlError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _DuplicateKey(ValueError):
    pass


class _ComplexKey(ValueError):
    pass


class RestrictedLoader(yaml.SafeLoader):
    """Safe YAML 1.2-ish loader constrained to JSON-compatible values."""


# Copy before modifying: PyYAML stores this table on the base class.
RestrictedLoader.yaml_implicit_resolvers = {
    initial: list(resolvers)
    for initial, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for initial, resolvers in list(RestrictedLoader.yaml_implicit_resolvers.items()):
    RestrictedLoader.yaml_implicit_resolvers[initial] = [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag
        not in {
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:timestamp",
        }
    ]

RestrictedLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)


def _construct_mapping(
    loader: RestrictedLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[str, Any]:
    if not isinstance(node, MappingNode):
        raise _ComplexKey("expected a mapping")
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, ScalarNode):
            raise _ComplexKey("YAML mapping keys must be scalar strings")
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise _ComplexKey("YAML mapping keys must be strings")
        if key in mapping:
            raise _DuplicateKey(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


RestrictedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


class RestrictedDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _ensure_json_compatible(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RestrictedYamlError(
                "yaml_value_not_json_compatible",
                f"non-finite number at {path}",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RestrictedYamlError(
                    "complex_yaml_key",
                    f"mapping key at {path} must be a string",
                )
            _ensure_json_compatible(item, f"{path}.{key}")
        return
    raise RestrictedYamlError(
        "yaml_value_not_json_compatible",
        f"unsupported value {type(value).__name__} at {path}",
    )


def load_restricted_yaml(text: str) -> dict[str, Any]:
    try:
        tokens = yaml.scan(text, Loader=RestrictedLoader)
        for token in tokens:
            if isinstance(token, (AnchorToken, AliasToken)):
                raise RestrictedYamlError(
                    "yaml_alias_forbidden",
                    "YAML anchors and aliases are forbidden",
                )
            if isinstance(token, TagToken):
                raise RestrictedYamlError(
                    "yaml_tag_forbidden",
                    "explicit YAML tags are forbidden",
                )
        value = yaml.load(text, Loader=RestrictedLoader)
    except RestrictedYamlError:
        raise
    except _DuplicateKey as error:
        raise RestrictedYamlError("duplicate_yaml_key", str(error)) from error
    except _ComplexKey as error:
        raise RestrictedYamlError("complex_yaml_key", str(error)) from error
    except yaml.MarkedYAMLError as error:
        raise RestrictedYamlError("invalid_yaml", str(error)) from error
    except (TypeError, ValueError) as error:
        raise RestrictedYamlError("invalid_yaml", str(error)) from error

    if not isinstance(value, dict):
        raise RestrictedYamlError(
            "front_matter_not_mapping",
            "YAML document must contain a top-level mapping",
        )
    _ensure_json_compatible(value)
    return value


def dump_restricted_yaml(value: Mapping[str, Any]) -> str:
    plain = dict(value)
    _ensure_json_compatible(plain)
    return yaml.dump(
        plain,
        Dumper=RestrictedDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )
