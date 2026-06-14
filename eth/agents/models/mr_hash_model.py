# eth/agents/models/mr_hash_model.py
"""
Model MR-Hash (MR-HBT-A2A)
===========================
Pipeline: Client → Agent → Consensus → Hash(온체인) + FullData(다중 오프체인) → Client

- 합의 후 결과의 SHA-256 해시만 온체인에 기록
- 풀 데이터는 db_count 개의 복제 오프체인 DB에 동시 저장
- 온체인 해시 + 과반수 검증으로 변조된 오프체인 DB를 탐지
- 과반수 검증 실패 시 자동 복구 수행 (MR-HBT-A2A 핵심 기능)
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Optional

from eth.agents.models.hash_model import HashAgent
from eth.agents.multi_offchain import MultiOffChainStore
from eth.agents.request import ClientRequest

log = logging.getLogger(__name__)


def _hash_result(result: Any) -> str:
    raw = json.dumps(result, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class MRHashAgent(HashAgent):
    """
    MR-Hash model: 해시 온체인 + 다중 복제 오프체인.

    Security : HIGH  — 온체인 해시 + 과반수 검증으로 단일 DB 변조를 탐지하고 복구.
    Speed    : MEDIUM — 단일 HashAgent와 동일한 합의 비용 + 복제 저장 오버헤드.
    """

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
            "[%s] MRHashAgent 초기화: %d개의 복제 DB 사용.", self.name, db_count
        )

    # ------------------------------------------------------------------
    # Storage: hash → on-chain, full data → ALL off-chain DBs
    # ------------------------------------------------------------------

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        풀 레코드의 SHA-256를 온체인에 기록하고, 풀 데이터를 모든 오프체인 DB에 복제 저장.

        MR-HBT-A2A는 HashAgent와 달리 result만이 아닌 전체 오프체인 레코드의 해시를
        온체인에 기록하여 메타데이터(votes, agent 등) 변조까지 탐지한다.
        """
        result_hash = _hash_result(result)

        # 오프체인에 저장할 풀 레코드를 먼저 구성
        record = {
            "request_id": request.request_id,
            "task": request.task,
            "payload": request.payload,
            "result": result,
            "result_hash": result_hash,
            "votes": consensus_result.get("votes", {}),
            "agent": self.name,
        }

        # 전체 레코드의 해시를 온체인에 기록 (majority_verify와 일치)
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

        # Off-chain: 모든 DB에 풀 데이터 복제 저장
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

    # ------------------------------------------------------------------
    # Verification with automatic recovery
    # ------------------------------------------------------------------

    def verify(self, request_id: str) -> bool:
        """
        온체인 해시를 기준으로 과반수 검증을 수행.
        과반수 검증 실패 시 자동으로 오프체인 DB를 복구한 뒤 결과를 반환.
        Returns True if majority verification passed (before or after recovery).
        """
        result = self.verify_with_recovery(request_id)
        return result["verified"]

    def verify_with_recovery(self, request_id: str) -> dict[str, Any]:
        """
        과반수 검증 전체 결과를 반환. 복구가 필요한 경우 복구 수행 후 결과 포함.

        Returns
        -------
        {
            "verified"           : bool,
            "recovery_attempted" : bool,
            "recovery_result"    : dict or None,
            "majority_result"    : dict
        }
        """
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

        # 과반수 검증 실패 → 복구 시도
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_onchain_hash(self, request_id: str) -> Optional[str]:
        """
        온체인 블록을 순회하여 request_id에 해당하는 record_hash를 반환.
        없으면 None.
        """
        for block_number in range(1, self.onchain.chain_length() + 1):
            block = self.onchain.get_block(block_number)
            if block is not None and block.data.get("request_id") == request_id:
                return block.data.get("record_hash")
        return None

    def __repr__(self) -> str:
        return (
            f"MRHashAgent("
            f"name={self.name!r}, "
            f"nodes={len(self.nodes)}, "
            f"offchain={self.offchain!r})"
        )
