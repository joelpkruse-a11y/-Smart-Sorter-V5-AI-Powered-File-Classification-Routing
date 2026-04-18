from typing import Dict, Any, List
from utils import log


def enhance_metadata(
    text: str,
    metadata_ai: Dict[str, Any] | None = None,
    metadata_vision: Dict[str, Any] | None = None,
    metadata_fs: Dict[str, Any] | None = None,
    tables: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Merge multiple metadata sources into a single, enriched dict.
    V6: now aware of tables and can promote key signals.
    """
    metadata_ai = metadata_ai or {}
    metadata_vision = metadata_vision or {}
    metadata_fs = metadata_fs or {}
    tables = tables or []

    merged: Dict[str, Any] = {}
    merged.update(metadata_fs)
    merged.update(metadata_vision)
    merged.update(metadata_ai)

    # Attach tables if present
    if tables:
        merged["tables"] = tables

    # Simple heuristics: promote some common fields if missing
    # (You can expand this with your own rules)
    if "document_type" not in merged and "category" in merged:
        merged["document_type"] = merged["category"]

    if text and "char_count" not in merged:
        merged["char_count"] = len(text)

    return merged