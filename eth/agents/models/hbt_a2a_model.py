from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from eth.agents.agent import Agent
from eth.agents.offchain import OffChainStore
from eth.agents.onchain import OnChainStore
from eth.agents.request import ClientRequest


def _hash_result(result: Any) -> str:
    raw = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class HBTA2AAgent(Agent):
    
    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable] = None,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        self.offchain = OffChainStore()
        self.onchain = OnChainStore()

    # ------------------------------------------------------------------
    # Storage: hash → on-chain, full data → off-chain
    # ------------------------------------------------------------------

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
        result_hash = _hash_result(result)

        # On-chain: minimal record — only the hash
        block = self.onchain.append(
            data={
                "request_id": request.request_id,
                "agent": self.name,
                "result_hash": result_hash,
            },
            votes=consensus_result.get("votes", {}),
        )

        # Off-chain: full record
        self.offchain.save(
            request.request_id,
            {
                "request_id": request.request_id,
                "task": request.task,
                "payload": request.payload,
                "result": result,
                "result_hash": result_hash,
                "votes": consensus_result.get("votes", {}),
                "agent": self.name,
            },
        )

        return {
            "mode": "hash",
            "onchain_block": block.number,
            "onchain_hash": block.hash[:16] + "…",
            "result_hash": result_hash[:16] + "…",
            "offchain_key": request.request_id,
            "secure": "partial",   # hash is secure, full data is not
        }

    def verify(self, request_id: str) -> bool:
        """
        Verify off-chain data integrity using the on-chain hash.
        Returns True if off-chain data matches the on-chain hash.
        """
        record = self.offchain.get(request_id)
        if record is None:
            return False
        expected_hash = record.get("result_hash")
        actual_hash = _hash_result(record.get("result"))
        return expected_hash == actual_hash
