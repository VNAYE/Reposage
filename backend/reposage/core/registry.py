"""Tiny factory registry used by every pluggable capability."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Maps a name to a factory. New implementations self-register."""

    def __init__(self, label: str) -> None:
        self._label = label
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        def decorator(factory: Callable[..., T]) -> Callable[..., T]:
            self._factories[name] = factory
            return factory

        return decorator

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        try:
            factory = self._factories[name]
        except KeyError:
            available = ", ".join(sorted(self._factories)) or "none"
            raise KeyError(f"unknown {self._label} {name!r} (available: {available})") from None
        return factory(*args, **kwargs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def __contains__(self, name: object) -> bool:
        return name in self._factories
