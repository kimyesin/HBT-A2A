from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Optional

from eth.agents.models.hbt_a2a_model import HBTA2AAgent
from eth.agents.multi_offchain import MultiOffChainStore
from eth.agents.request import ClientRequest

log = logging.getLogger(__name__)


def _hash_result(result: Any) -> str:
    raw = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class TrustworthyA2AAgent(HBTA2AAgent):


    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable[[str, Any], Any]] = None,
        db_count: int = 3,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        # 단일 OffChainStore를 MultiOffChainStore로 교체
        self.offchain: MultiOffChainStore = MultiOffChainStore(db_count=db_count)
        # self.onchain은 HashAgent(→ Agent)로부터 그대로 상속

        log.info(
            "[%s] TrustworthyA2AAgent 초기화: %d개의 복제 DB 사용.", self.name, db_count
        )

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
    
        result_hash = _hash_result(result)

        record = {
            "request_id": request.request_id,
            "task": request.task,
            "payload": request.payload,
            "result": result,
            "result_hash": result_hash,
            "votes": consensus_result.get("votes", {}),
            "agent": self.name,
        }

        record_hash = hashlib.sha256(
            json.dumps(record, sort_keys=True, default=str).encode()
        ).hexdigest()

        block = self.onchain.append(
            data={
                "request_id": request.request_id,
                "agent": self.name,
                "record_hash": record_hash,
            },
            votes=consensus_result.get("votes", {}),
        )

        self.offchain.save(request.request_id, record)

        db_count = self.offchain._db_count
        log.info(
            "[%s] _store_result: block=#%d, record_hash=%s, DB 복제=%d개.",
            self.name, block.number, record_hash[:16], db_count,
        )

        return {
            "mode": "mr_hash",
            "onchain_block": block.number,
            "onchain_hash": block.hash[:16] + "…",
            "result_hash": result_hash[:16] + "…",
            "db_count": db_count,
            "secure": "partial",
        }

    def verify(self, request_id: str) -> bool:
        
        result = self.verify_with_recovery(request_id)
        return result["verified"]

    def verify_with_recovery(self, request_id: str) -> dict[str, Any]:
       
        onchain_hash = self._get_onchain_hash(request_id)
        if onchain_hash is None:
            log.warning("[%s] verify: request_id=%r 온체인 해시 없음.", self.name, request_id)
            return {
                "verified": False,
                "recovery_attempted": False,
                "recovery_result": None,
                "majority_result": {
                    "valid": False,
                    "match_count": 0,
                    "total_count": self.offchain._db_count,
                    "bad_db_indices": list(range(self.offchain._db_count)),
                },
            }

        majority_result = self.offchain.majority_verify(request_id, onchain_hash)

        if majority_result["valid"]:
            return {
                "verified": True,
                "recovery_attempted": False,
                "recovery_result": None,
                "majority_result": majority_result,
            }

        log.warning(
            "[%s] verify: request_id=%r 과반수 검증 실패 — 복구 시도.",
            self.name, request_id,
        )
        recovery_result = self.offchain.recover(request_id)

        return {
            "verified": recovery_result["recovered"],
            "recovery_attempted": True,
            "recovery_result": recovery_result,
            "majority_result": majority_result,
        }

    def _get_onchain_hash(self, request_id: str) -> Optional[str]:
        
        for block_number in range(1, self.onchain.chain_length() + 1):
            block = self.onchain.get_block(block_number)
            if block is not None and block.data.get("request_id") == request_id:
                return block.data.get("record_hash")
        return None

    def __repr__(self) -> str:
        return (
            f"TrustworthyA2AAgent("
            f"name={self.name!r}, "
            f"nodes={len(self.nodes)}, "
            f"offchain={self.offchain!r})"
        )
