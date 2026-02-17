"""Custom checkpoint serde that strips non-serializable callables before saving.

LangGraph checkpoints are serialized with msgpack. If state (or config) ever
contains a function (e.g. a callback), serialization fails with
"Type is not msgpack serializable: function". This wrapper recursively removes
callables so checkpoint save succeeds. Deserialization is unchanged.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def _strip_callables(obj: Any) -> Any:
    """Return a copy of obj with callables removed so msgpack can serialize."""
    if callable(obj):
        return None
    if isinstance(obj, dict):
        return {k: _strip_callables(v) for k, v in obj.items() if not callable(v)}
    if isinstance(obj, list):
        return [_strip_callables(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_strip_callables(x) for x in obj)
    return obj


class SafeCheckpointSerde(SerializerProtocol):
    """Wraps JsonPlusSerializer and strips callables before dumps_typed."""

    def __init__(self) -> None:
        self._serde: SerializerProtocol = JsonPlusSerializer()

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        clean = _strip_callables(obj)
        return self._serde.dumps_typed(clean)

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        return self._serde.loads_typed(data)
