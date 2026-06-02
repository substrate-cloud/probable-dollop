"""`Secret` sentinel — secrets stay out of __repr__, logs, and YAML dumps.

Resolution happens at the *submission* boundary (the moment we render a
LaunchConfiguration). If a user logs a Workload object, secrets stay redacted.

Built-in sources:
  Secret.from_env("HF_TOKEN")    → reads os.environ at submit time
  Secret.literal("hf_xxx")       → testing only; emits a warning
  Secret.from_callable(fn)       → bring-your-own (Vault, AWS SM, GCP SM, ...)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("substratecloud.workloads.secret")


class Secret:
    """Opaque reference to a secret resolved at submission time."""

    __slots__ = ("_provider", "_label", "_origin")

    def __init__(self, provider: Callable[[], str], *, label: str, origin: str) -> None:
        self._provider = provider
        self._label = label
        self._origin = origin

    # -- constructors ---------------------------------------------------------

    @classmethod
    def from_env(cls, name: str) -> Secret:
        def _read() -> str:
            val = os.environ.get(name)
            if val is None:
                raise KeyError(f"Secret env var {name!r} is not set")
            return val

        return cls(_read, label=name, origin=f"env:{name}")

    @classmethod
    def literal(cls, value: str, *, label: str = "literal") -> Secret:
        """Use only in tests / dev. Emits a warning to remind you."""
        _log.warning(
            "substratecloud.secret.literal_used",
            extra={"label": label},
        )
        return cls(lambda: value, label=label, origin="literal")

    @classmethod
    def from_callable(cls, fn: Callable[[], str], *, label: str, origin: str = "callable") -> Secret:
        return cls(fn, label=label, origin=origin)

    # -- resolution -----------------------------------------------------------

    def resolve(self) -> str:
        return self._provider()

    @property
    def origin(self) -> str:
        return self._origin

    # -- safety ---------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Secret(label={self._label!r}, origin={self._origin!r}, value=***)"

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other: Any) -> bool:  # noqa: D401
        return isinstance(other, Secret) and other._origin == self._origin

    def __hash__(self) -> int:
        return hash(("Secret", self._origin))


def resolve_value(v: str | Secret) -> str:
    """Helper: unwrap a Secret if needed, else return the str as-is."""
    return v.resolve() if isinstance(v, Secret) else v
