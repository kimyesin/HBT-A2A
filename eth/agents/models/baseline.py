"""
Model 1: Baseline
=================
Pipeline: Client → Agent (no consensus) → OffChain → Client

- 합의 과정 없음 — 에이전트가 결과를 바로 오프체인에 저장
- 가장 빠른 처리 속도
- 오프체인이므로 덮어쓰기 공격에 취약 (읽기/쓰기 모두 가능)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from eth.agents.agent import Agent
from eth.agents.offchain import OffChainStore
from eth.agents.request import ClientRequest


class BaselineAgent(Agent):
    """
    Baseline model: off-chain only, no internal consensus.

    Security : LOW   — attacker can read and overwrite records.
    Speed    : HIGH  — no consensus round, direct off-chain write.
    """

    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable] = None,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        self.offchain = OffChainStore()

    # ------------------------------------------------------------------
    # Skip consensus — Baseline does not need blockchain agreement
    # ------------------------------------------------------------------

    def _run_consensus(self, task: str, result: Any) -> dict[str, Any]:
        """Baseline bypasses consensus entirely."""
        return {"consensus_reached": False, "votes": {}, "skipped": True}

    # ------------------------------------------------------------------
    # Store directly to off-chain (no vote verification)
    # ------------------------------------------------------------------

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "request_id": request.request_id,
            "task": request.task,
            "payload": request.payload,
            "result": result,
            "agent": self.name,
        }
        self.offchain.save(request.request_id, record)
        return {
            "mode": "baseline",
            "location": "offchain",
            "key": request.request_id,
            "secure": False,      # attacker can overwrite
        }
