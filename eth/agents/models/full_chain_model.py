from __future__ import annotations

from typing import Any, Callable, Optional

from eth.agents.agent import Agent
from eth.agents.onchain import OnChainStore
from eth.agents.request import ClientRequest


class FullChainAgent(Agent):


    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable] = None,
    ) -> None:
        super().__init__(name, node_count, task_handler)
        self.onchain = OnChainStore()

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
