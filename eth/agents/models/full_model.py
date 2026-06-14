"""
Model 3: Full
=============
Pipeline: Client → Agent → Consensus → AllData(온체인) → Client

- 합의 후 모든 데이터(요청, 결과, 투표 내역)를 온체인에 기록
- 가장 높은 보안 수준 — 공격자는 읽기만 가능, 쓰기 불가
- 합의 노드 수만큼 검증이 필요하므로 처리 속도가 가장 느림
- 데이터 무결성 완전 보장 (변조 불가)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from eth.agents.agent import Agent
from eth.agents.onchain import OnChainStore
from eth.agents.request import ClientRequest


class FullAgent(Agent):
    """
    Full model: all data stored on-chain after consensus.

    Security : HIGH  — append-only chain; attacker can only read.
    Speed    : LOW   — full consensus + per-node verification before write.
    """

    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable] = None,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        self.onchain = OnChainStore()

    # ------------------------------------------------------------------
    # Storage: everything → on-chain (requires consensus votes)
    # ------------------------------------------------------------------

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
        block = self.onchain.append(
            data={
                "request_id": request.request_id,
                "task": request.task,
                "payload": request.payload,
                "result": result,
                "agent": self.name,
                "consensus_reached": consensus_result.get("consensus_reached"),
                "approved": consensus_result.get("approved_count"),
                "total_nodes": consensus_result.get("total_count"),
                "votes": {
                    node_id: v.get("approve")
                    for node_id, v in consensus_result.get("votes", {}).items()
                },
            },
            votes=consensus_result.get("votes", {}),
        )

        return {
            "mode": "full",
            "onchain_block": block.number,
            "onchain_hash": block.hash[:16] + "…",
            "chain_length": self.onchain.chain_length(),
            "chain_intact": self.onchain.verify_integrity(),
            "secure": True,        # attacker cannot overwrite
        }
