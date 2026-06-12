"""
OffChainStore — off-chain data store (no consensus required).

Characteristics:
  - FAST: writes happen immediately, no consensus round needed.
  - INSECURE: attacker can both read AND overwrite any record.
    There is no append-only guarantee — any process with access
    can call save() with an existing key and silently replace data.
"""
from __future__ import annotations

import threading
from typing import Any, Optional


class OffChainStore:
    """
    Thread-safe in-memory off-chain store.

    Security model
    --------------
    Read  : anyone with a reference can read.
    Write : anyone with a reference can overwrite — no protection.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, key: str, record: dict[str, Any]) -> None:
        """
        Persist a record directly (no validation, no consensus).
        If `key` already exists the record is silently overwritten.
        """
        with self._lock:
            self._store[key] = record

    def get(self, key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._store.get(key)

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._store.values())

    # ------------------------------------------------------------------ #
    # Attack surface demo — shows why off-chain is insecure               #
    # ------------------------------------------------------------------ #

    def overwrite_attack(self, key: str, forged_data: dict[str, Any]) -> bool:
        """
        Simulates a file-overwrite attack.
        Returns True if the target record existed and was overwritten.
        """
        with self._lock:
            if key in self._store:
                self._store[key] = forged_data   # silently replaced
                return True
            return False

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self) -> str:
        return f"OffChainStore(records={len(self._store)})"
