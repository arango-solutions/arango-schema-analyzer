from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_AQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_aql_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _AQL_IDENT_RE.match(value):
        raise ValueError(f"Invalid AQL identifier for {name}")


def stable_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entity_property_names(entity: dict[str, Any]) -> list[str]:
    """
    Return the property-name list declared on a schema entity, tolerating
    every shape the analyzer ever emits.

    Three shapes are accepted:

    * ``properties`` is a **dict** keyed by property name (the
      ``physicalMapping.entities[*].properties`` shape used by the LLM
      output and by ``infer_baseline_from_snapshot``).
    * ``properties`` is a **list of dicts** with a ``name`` key (the
      ``conceptualSchema.entities[*].properties`` shape).
    * ``properties`` is a **list of bare strings** (older fixtures /
      truncated LLM output).

    Any other shape (including ``None``) yields ``[]``. Order of the
    returned list mirrors the input order; callers that need a stable
    order should sort.
    """
    props = entity.get("properties")
    if isinstance(props, dict):
        return [str(k) for k in props]
    if isinstance(props, list):
        out: list[str] = []
        for item in props:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and isinstance(item.get("name"), str):
                out.append(item["name"])
        return out
    return []


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_domain_tokens(name: str) -> list[str]:
    """Lowercase ``name`` and split on common separators (``-`` / ``_``),
    returning the non-empty token list.

    Used by domain-detection scoring to derive matchable keyword tokens
    from collection / graph / type-value names. Empty input or
    non-strings yield ``[]``.
    """
    if not isinstance(name, str) or not name:
        return []
    return [p for p in name.lower().replace("-", "_").split("_") if p]


def iter_edge_definitions(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Yield well-formed ``edge_definitions`` records from a snapshot
    graph entry, dropping any malformed (non-dict / no-collection) rows.

    Centralises the common ``for ed in graph.get("edge_definitions") or []:
    if not isinstance(ed, dict): continue ...`` pattern that previously
    appeared in ``baseline.py`` and ``sharding_profile.py``.
    """
    out: list[dict[str, Any]] = []
    for ed in graph.get("edge_definitions") or []:
        if not isinstance(ed, dict):
            continue
        col = ed.get("collection")
        if not isinstance(col, str) or not col:
            continue
        out.append(ed)
    return out


def index_edge_definitions_by_collection(
    graphs: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Build a deterministic ``{edge_collection_name: edge_def}`` index
    over every named graph in ``graphs``.

    When two graphs declare the same edge collection the
    lexicographically first graph name wins (callers that rely on this
    determinism include sharding-profile classification and baseline
    endpoint enrichment).
    """
    out: dict[str, dict[str, Any]] = {}
    if not graphs:
        return out
    for g in sorted(graphs, key=lambda x: str(x.get("name") or "")):
        if not isinstance(g, dict):
            continue
        for ed in iter_edge_definitions(g):
            out.setdefault(str(ed["collection"]), ed)
    return out


def normalize_analysis_dict(analysis: Any) -> dict[str, Any]:
    """
    Coerce an ``AnalysisResult`` (pydantic model) or already-serialized
    dict into a plain ``dict`` and normalize the snake_case vs camelCase
    aliases under the ``conceptual_schema`` / ``physical_mapping`` keys.

    Returns a shallow copy where:

    * ``conceptualSchema`` is always present (sourced from
      ``conceptual_schema`` if needed) — and ``conceptual_schema`` is
      removed once it has been hoisted.
    * ``physicalMapping`` is always present (sourced from
      ``physical_mapping`` if needed) — and ``physical_mapping`` is
      removed once it has been hoisted.

    Centralises the conversion the OWL / docs / cypher exporters used to
    repeat (``analysis.model_dump() if hasattr(...) else analysis`` plus
    ``data.get("conceptual_schema") or data.get("conceptualSchema")``).
    """
    if hasattr(analysis, "model_dump"):
        data = dict(analysis.model_dump())
    elif isinstance(analysis, dict):
        data = dict(analysis)
    else:
        raise TypeError(f"normalize_analysis_dict: unsupported type {type(analysis).__name__}")

    if "conceptualSchema" not in data and "conceptual_schema" in data:
        data["conceptualSchema"] = data.pop("conceptual_schema")
    elif "conceptual_schema" in data:
        data.pop("conceptual_schema")

    if "physicalMapping" not in data and "physical_mapping" in data:
        data["physicalMapping"] = data.pop("physical_mapping")
    elif "physical_mapping" in data:
        data.pop("physical_mapping")

    return data


def analysis_cache_storage_key(physical_fingerprint: str, *, llm_cache_segment: str | None) -> str:
    """
    Filesystem-safe cache filename stem.

    Baseline / no-LLM analysis is keyed only by the physical schema fingerprint.
    LLM runs also incorporate prompt version and effective system prompt so cache
    entries do not collide when prompts differ.
    """
    if not llm_cache_segment:
        return physical_fingerprint
    return sha256_hex(f"{physical_fingerprint}\n{llm_cache_segment}")


_IE_SINGULAR_ROOTS = frozenset(
    {
        "movie",
        "zombie",
        "cookie",
        "brownie",
        "rookie",
        "selfie",
        "genie",
        "smoothie",
        "collie",
        "magpie",
        "birdie",
        "calorie",
        "prairie",
        "reverie",
        "sortie",
        "lingerie",
    }
)


def singularize(name: str) -> str:
    """Best-effort English singularization for collection/entity names.

    Suffixes match case-insensitively, and a replacement letter follows the case of
    the letter it replaces, so ``CUSTOMERS`` -> ``CUSTOMER`` and ``CATEGORIES`` ->
    ``CATEGORY``. Upper-case names used to come back unchanged, which hid every
    relationship to an upper-case collection from FK inference -- the fix
    relational-schema-analyzer 0.9.0 and r2g 0.4.2 made to their copies.
    ``csi.naming.singularize`` was already case-insensitive.
    """
    n = name.strip()
    lower = n.lower()
    if lower.endswith("ies") and len(n) > 3:
        # Distinguish consonant+y→consonant+ies (city→cities) from root-ie+s (movie→movies).
        # Words whose singular ends in "-ie" should just drop the "s".
        without_s = n[:-1]
        if without_s.lower() in _IE_SINGULAR_ROOTS:
            return without_s
        return n[:-3] + ("Y" if n[-3].isupper() else "y")
    if lower.endswith("sses") and len(n) > 4:
        return n[:-2]
    if lower.endswith("s") and not lower.endswith("ss") and len(n) > 1:
        return n[:-1]
    return n


def pascal_case(name: str) -> str:
    """Convert snake_case, kebab-case, or space-separated name to PascalCase."""
    parts = [p for p in str(name).replace("-", "_").replace(" ", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Unknown"


def extract_first_json_object(text: str) -> str:
    """
    Extract the first top-level JSON object from a string.
    Works with model outputs that include preamble/postamble.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object start found")

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise ValueError("Unterminated JSON object")
