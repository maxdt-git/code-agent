"""
API keys loading (PREFIX, PREFIX_1, PREFIX_2...) and rotation.
A key value is never printed: logs use its env var name.
"""
from collections.abc import Mapping
import os


def load_keys(
        prefix: str,
        environ: Mapping[str, str]
) -> list[tuple[str, str]]:
    """
    Take a dict (API keys) and returns the non empty keys named prefix or
    prefix_<n>, sorted by n, without duplicate, as pairs
    """
    found: list[tuple[int, str, str]] = []
    for name, value in environ.items():
        if name.startswith(prefix):
            rest = name[len(prefix):]
            if not rest or (rest[0] == "_" and rest[1:].isdigit()):
                v = value.strip()
                if v != "":
                    num = 0 if not rest else int(rest[1:])
                    found.append((num, name, v))

    seen_keys: set[str] = set()
    result: list[tuple[str, str]] = []
    for _, name, v in sorted(found):
        if v not in seen_keys:
            seen_keys.add(v)
            result.append((name, v))

    return result


class KeyPool:
    """
    Go through the API keys of a provider, skipping disabled ones
    """
    def __init__(
            self,
            prefix: str,
            environ: Mapping[str, str] | None = None
    ) -> None:
        self.prefix: str = prefix
        if environ is None:
            environ = os.environ
        self._keys: list[tuple[str, str]] = load_keys(prefix, environ)
        self._index: int = 0
        self._disabled: set[int] = set()

    @property
    def live_count(self) -> int:
        """
        Number of available keys
        """
        return len(self._keys) - len(self._disabled)

    def current(self) -> tuple[str, str] | None:
        """
        Find the current key and return (name, key) or None
        if key is disabled
        """
        if self.live_count == 0:
            return None
        if self._index in self._disabled:
            self.rotate()
        return self._keys[self._index]

    def rotate(self) -> None:
        """
        Loop through the key to find the next available key,
        and does nothing if no key finds
        """
        for _ in range(len(self._keys)):
            self._index = (self._index + 1) % len(self._keys)
            if self._index not in self._disabled:
                return

    def disable_current(self) -> None:
        """
        Disable the current key and find other one
        """
        if not self._keys:
            return
        self._disabled.add(self._index)
        self.rotate()
