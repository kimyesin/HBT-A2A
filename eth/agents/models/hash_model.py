"""
Model 2: Hash
=============
Pipeline: Client → Agent → Consensus → Hash(온체인) + FullData(오프체인) → Client

- 합의 후 결과의 SHA-256 해시만 온체인에 기록  (최소한의 온체인 데이터)
- 풀 데이터는 오프체인에 저장
- 온체인 해시로 오프체인 데이터의 무결성을 검증할 수 있음
  (해시가 맞으면 데이터가 변조되지 않았음을 보장)
- 오프체인은 여전히 덮어쓰기 공격에 취약하나,
  온체인 해시를 통해 변조 여부를 탐지 가능
"""
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


class HashAgent(Agent):
    """
    Hash model: hash on-chain, full data off-chain.

    Security : MEDIUM — on-chain hash proves data integrity;
                         off-chain full data is still overwritable,
                         but tampering is detectable via hash mismatch.
    Speed    : MEDIUM  — consensus required before on-chain write.
    """

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
