from __future__ import annotations

from typing import Any, Callable, Optional

from eth.agents.agent import Agent
from eth.agents.offchain import OffChainStore
from eth.agents.request import ClientRequest


class BaselineAgent(Agent):

    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable] = None,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        self.offchain = OffChainStore()

    def _run_consensus(self, task: str, result: Any) -> dict[str, Any]:
        """Baseline bypasses consensus entirely."""
        return {"consensus_reached": False, "votes": {}, "skipped": True}

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
