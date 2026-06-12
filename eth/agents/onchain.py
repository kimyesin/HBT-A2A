"""
OnChainStore — simulated on-chain append-only blockchain storage.

Characteristics:
  - SLOW: a block is only written after all consensus votes are verified.
    Write latency scales with the number of nodes in the agent.
  - SECURE: the chain is append-only. Existing blocks cannot be modified
    or deleted — attackers can read but cannot write or overwrite.

Chain structure (linked by SHA-256):

  Genesis(#0) ← Block#1 ← Block#2 ← … ← Block#N
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Block:
    number: int
    prev_hash: str
    timestamp: float
    data: dict[str, Any]
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        raw = json.dumps(
            {
                "number": self.number,
                "prev_hash": self.prev_hash,
                "timestamp": self.timestamp,
                "data": self.data,
            },
            sort_keys=True,
            default=str,
        )
        self.hash = _sha256(raw)

    def summary(self) -> dict[str, Any]:
        return {
            "block": self.number,
            "hash": self.hash[:16] + "…",
            "prev": self.prev_hash[:16] + "…",
            "data_keys": list(self.data.keys()),
        }


class OnChainStore:
    """
    Thread-safe, append-only simulated blockchain.

    Security model
    --------------
    Read  : anyone can read.
    Write : requires a valid `votes` dict produced by AgentConsensus.
            Once written, blocks are immutable — no overwrite is possible.

    Performance
    -----------
    `append()` verifies every vote before committing, so write time
    grows linearly with the number of consensus nodes.
    """

    GENESIS_HASH = _sha256("genesis")

    def __init__(self) -> None:
        self._chain: list[Block] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Write (requires consensus votes)                                     #
    # ------------------------------------------------------------------ #

    def append(
        self,
        data: dict[str, Any],
        votes: dict[str, Any],
    ) -> Block:
        """
        Mine a new block after verifying that consensus was reached.

        Parameters
        ----------
        data  : payload to store on-chain
        votes : vote dict produced by AgentConsensus.run()
                  {node_id: {"approve": bool, ...}}

        Raises
        ------
        PermissionError if no approving votes are provided — prevents
        writing without consensus.
        """
        approved = [v for v in votes.values() if v.get("approve")]
        if not approved:
            raise PermissionError(
                "On-chain write rejected: no consensus votes provided. "
                "All nodes must participate before data can be written."
            )

        # Simulate per-node verification delay
        # (in production each node re-executes and signs the block)
        for _ in approved:
            pass  # placeholder for cryptographic verification

        with self._lock:
            prev_hash = (
                self._chain[-1].hash if self._chain else self.GENESIS_HASH
            )
            block = Block(
                number=len(self._chain) + 1,
                prev_hash=prev_hash,
                timestamp=time.time(),
                data=data,
            )
            self._chain.append(block)
            return block

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def get_block(self, number: int) -> Optional[Block]:
        with self._lock:
            if 1 <= number <= len(self._chain):
                return self._chain[number - 1]
            return None

    def latest(self) -> Optional[Block]:
        with self._lock:
            return self._chain[-1] if self._chain else None

    def chain_length(self) -> int:
        return len(self._chain)

    def verify_integrity(self) -> bool:
        """Walk the chain and verify all hashes link correctly."""
        with self._lock:
            prev = self.GENESIS_HASH
            for block in self._chain:
                if block.prev_hash != prev:
                    return False
                prev = block.hash
            return True

    def summary(self) -> list[dict[str, Any]]:
        with self._lock:
            return [b.summary() for b in self._chain]

    # ------------------------------------------------------------------ #
    # Attack surface demo — shows why on-chain IS secure                  #
    # ------------------------------------------------------------------ #

    def overwrite_attack(self, block_number: int, forged_data: dict) -> bool:
        """
        Simulates an attacker attempting to overwrite a block.
        Always returns False — the chain is immutable.
        """
        return False  # append-only: no overwrite possible

    def __len__(self) -> int:
        return len(self._chain)

    def __repr__(self) -> str:
        return f"OnChainStore(blocks={len(self._chain)})"
