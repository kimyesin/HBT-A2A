"""
AgentConsensus — majority-vote consensus among an Agent's nodes.

Protocol (per request):
  1. Leader node (index 0) produces a result by executing the task.
  2. All nodes vote on (task, proposed_result).
  3. If strictly more than half approve  → consensus reached.
  4. On consensus all nodes commit the block locally.
  5. Result (+ vote tally) is returned to the Agent.
"""
from __future__ import annotations

import logging
from typing import Any

from eth.agents.node import AgentNode

log = logging.getLogger(__name__)


class AgentConsensus:
    """Runs a single consensus round over a list of AgentNodes."""

    def __init__(self, nodes: list[AgentNode], threshold: float = 0.5) -> None:
        if not nodes:
            raise ValueError("AgentConsensus requires at least one node.")
        self.nodes = nodes
        # fraction of nodes that must approve  (default: strict majority)
        self.threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        proposed_result: Any,
    ) -> dict[str, Any]:
        """
        Execute a consensus round.

        Parameters
        ----------
        task:            human-readable task string
        proposed_result: the value every node votes on

        Returns
        -------
        dict with keys:
            consensus_reached  bool
            votes              {node_id: vote_dict}
            approved_count     int
            total_count        int
            committed_root     str | None   (state root after commit)
        """
        votes: dict[str, Any] = {}
        approved = 0

        for node in self.nodes:
            vote = node.propose_vote(task, proposed_result)
            votes[node.node_id] = vote
            if vote["approve"]:
                approved += 1

        total = len(self.nodes)
        reached = (approved / total) > self.threshold

        log.info(
            "Consensus round: approved=%d/%d  reached=%s",
            approved, total, reached,
        )

        committed_root: str | None = None
        if reached:
            # All nodes commit the new block
            for node in self.nodes:
                committed_root = node.commit(proposed_result)

        return {
            "consensus_reached": reached,
            "votes": votes,
            "approved_count": approved,
            "total_count": total,
            "committed_root": committed_root,
        }
