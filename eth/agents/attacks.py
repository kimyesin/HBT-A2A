# eth/agents/attacks.py
"""
Attack simulation utilities.

An attacker overwrites data that an agent has ALREADY stored
(on-chain or off-chain) with forged data. The attacker cannot read
the original content — it only overwrites.

Attack parameters
------------------
- Intensity (KB): how much data is overwritten per attack call.
  The number of records to attack is derived from intensity_kb
  divided by the average size of records currently stored.
- Frequency: how often an attack occurs, controlled by the caller
  (e.g. benchmark/demo scripts) — e.g. "attack every N requests".

Attacker types
--------------
1. On-chain attacker         — attempts to overwrite the most recent
                                 block(s). Always fails (append-only chain).
2. Single off-chain attacker  — overwrites the most recent record(s)
                                 in DB1 (used by Baseline, HBT-A2A).
3. Multi off-chain attacker    — overwrites the most recent record(s)
                                 in one DB, chosen randomly among
                                 DB1~DBn (used by Trustworthy A2A).
"""
from __future__ import annotations

import json
import random
from typing import Any

from eth.agents.offchain import OffChainStore
from eth.agents.onchain import OnChainStore
from eth.agents.multi_offchain import MultiOffChainStore


FORGED_RECORD: dict[str, Any] = {"attack": True, "forged": True}


def _record_size_kb(record: dict[str, Any]) -> float:
    """Return the size of a record in KB when serialized as JSON."""
    return len(json.dumps(record, default=str)) / 1024


def _records_to_attack(store_values: list[dict[str, Any]], intensity_kb: float) -> int:
    """
    Given the currently stored records and an attack intensity (KB),
    return how many of the most recent records should be overwritten.

    The average size of existing records is used to convert
    intensity_kb into a record count. At least 1 record is attacked
    if any data exists and intensity_kb > 0.
    """
    if not store_values or intensity_kb <= 0:
        return 0

    avg_size_kb = sum(_record_size_kb(r) for r in store_values) / len(store_values)
    if avg_size_kb <= 0:
        return 0

    n = round(intensity_kb / avg_size_kb)
    return max(1, min(n, len(store_values)))


# ----------------------------------------------------------------------
# Attacker 1 — On-chain
# ----------------------------------------------------------------------

def attack_onchain(store: OnChainStore, intensity_kb: float) -> int:
    """
    Attempt to overwrite the most recent block(s) on-chain.

    Always returns 0 successful overwrites — the append-only chain
    structurally rejects all overwrite attempts (see
    OnChainStore.overwrite_attack, which always returns False).

    Returns
    -------
    int : number of blocks successfully overwritten (always 0).
    """
    chain_length = store.chain_length()
    if chain_length == 0 or intensity_kb <= 0:
        return 0

    blocks = [store.get_block(n) for n in range(1, chain_length + 1)]
    block_dicts = [b.data for b in blocks if b is not None]
    n_targets = _records_to_attack(block_dicts, intensity_kb)

    success = 0
    for block_number in range(chain_length, chain_length - n_targets, -1):
        if store.overwrite_attack(block_number, dict(FORGED_RECORD)):
            success += 1
    return success


# ----------------------------------------------------------------------
# Attacker 2 — Single off-chain (DB1)
# ----------------------------------------------------------------------

def attack_offchain(store: OffChainStore, intensity_kb: float) -> int:
    """
    Overwrite the most recently stored record(s) in a single
    off-chain store (DB1). Used by Baseline and HBT-A2A.

    Returns
    -------
    int : number of records successfully overwritten.
    """
    keys = list(store._store.keys())
    if not keys or intensity_kb <= 0:
        return 0

    values = list(store._store.values())
    n_targets = _records_to_attack(values, intensity_kb)

    success = 0
    for key in keys[-n_targets:]:
        if store.overwrite_attack(key, dict(FORGED_RECORD)):
            success += 1
    return success


# ----------------------------------------------------------------------
# Attacker 3 — Multi-replica off-chain (DB1~DBn, random selection)
# ----------------------------------------------------------------------

def attack_multi_offchain(
    store: MultiOffChainStore,
    intensity_kb: float,
) -> dict[str, Any]:
    """
    intensity_kb를 DB 수로 나눠서 각 DB당 공격 강도를 계산.
    강도가 클수록 더 많은 DB를 동시에 공격.
    """
    db_count = store._db_count
    per_db_intensity = intensity_kb / db_count  # DB당 할당 강도
    
    total_attacked = 0
    attacked_dbs = []
    for i in range(db_count):
        n = attack_offchain(store._stores[i], per_db_intensity)
        if n > 0:
            total_attacked += n
            attacked_dbs.append(i)

    return {"attacked_dbs": attacked_dbs, "total_attacked": total_attacked}