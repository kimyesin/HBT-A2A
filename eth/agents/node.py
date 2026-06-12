"""
AgentNode — a single node living inside an Agent.

Each node:
- Holds a local view of the blockchain (block number + state hash).
- Receives a task proposal from its Agent and casts a vote.
- Votes are simple majority: the node validates the proposed result and
  returns True/False.  Agents collect votes and decide consensus.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

log = logging.getLogger(__name__)


class AgentNode:
    """A participant node within an Agent's internal consensus round."""

    def __init__(self, node_id: str, agent_name: str) -> None:
        self.node_id = node_id
        self.agent_name = agent_name

        # Local blockchain view — block number and a state digest
        self._block_number: int = 0
        self._state_root: str = self._compute_genesis_root()

    # ------------------------------------------------------------------
    # Blockchain state helpers
    # ------------------------------------------------------------------

    def _compute_genesis_root(self) -> str:
        return hashlib.sha256(b"genesis").hexdigest()

    def _advance_block(self, result_data: Any) -> str:
        """Simulate committing a new block and return the new state root."""
        self._block_number += 1
        payload = f"{self._state_root}:{self._block_number}:{result_data}"
        self._state_root = hashlib.sha256(payload.encode()).hexdigest()
        return self._state_root

    @property
    def block_number(self) -> int:
        return self._block_number

    @property
    def state_root(self) -> str:
        return self._state_root

    # ------------------------------------------------------------------
    # Consensus participation
    # ------------------------------------------------------------------

    def propose_vote(self, task: str, proposed_result: Any) -> dict[str, Any]:
        """
        Validate the proposed result and return a vote dict.

        In a real system this would verify Merkle proofs, re-execute
        the transaction, or check BFT certificates.  Here we perform a
        lightweight sanity check and always agree if the proposed_result
        is non-None.
        """
        valid = proposed_result is not None and task != ""
        vote = {
            "node_id": self.node_id,
            "approve": valid,
            "block_number": self._block_number,
            "state_root": self._state_root,
        }
        log.debug(
            "[%s/%s] vote for task=%r → %s",
            self.agent_name, self.node_id, task, "APPROVE" if valid else "REJECT",
        )
        return vote

    def commit(self, result_data: Any) -> str:
        """Commit a consensus-approved result and advance the local chain."""
        new_root = self._advance_block(result_data)
        log.debug(
            "[%s/%s] committed block #%d  root=%s",
            self.agent_name, self.node_id, self._block_number, new_root[:12],
        )
        return new_root

    def __repr__(self) -> str:
        return (
            f"AgentNode(id={self.node_id}, agent={self.agent_name}, "
            f"block={self._block_number})"
        )
