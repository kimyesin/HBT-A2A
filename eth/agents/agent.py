"""
Agent — base autonomous agent.

Subclasses implement `_store_result()` to choose the storage model:
  - BaselineAgent : off-chain only   (no consensus, fast, insecure)
  - HashAgent     : hash on-chain + full off-chain
  - FullAgent     : everything on-chain (slow, secure)
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

from eth.agents.consensus import AgentConsensus
from eth.agents.node import AgentNode
from eth.agents.request import ClientRequest, ClientResponse

log = logging.getLogger(__name__)


class Agent:
    """
    Base autonomous blockchain agent.

    Parameters
    ----------
    name:         human-readable identifier (e.g. "Agent-A")
    node_count:   number of internal consensus nodes
    task_handler: optional callable(task, payload) → result
    """

    def __init__(
        self,
        name: str,
        node_count: int = 3,
        task_handler: Optional[Callable[[str, Any], Any]] = None,
    ) -> None:
        self.name = name
        self._task_handler = task_handler

        self.nodes: list[AgentNode] = [
            AgentNode(node_id=f"{name}-node-{i}", agent_name=name)
            for i in range(node_count)
        ]
        self._consensus = AgentConsensus(self.nodes)

        self._queue: queue.Queue[
            tuple[ClientRequest, Callable[[ClientResponse], None]]
        ] = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        log.info("[%s] initialised with %d nodes.", self.name, node_count)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, name=f"{self.name}-worker", daemon=True
        )
        self._thread.start()
        log.info("[%s] started.", self.name)

    def stop(self, timeout: float = 5.0) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info("[%s] stopped.", self.name)

    # ------------------------------------------------------------------
    # Client-facing API
    # ------------------------------------------------------------------

    def submit(
        self,
        request: ClientRequest,
        callback: Callable[[ClientResponse], None],
    ) -> None:
        """Non-blocking: enqueue a request."""
        self._queue.put((request, callback))

    def handle(self, request: ClientRequest) -> ClientResponse:
        """Blocking: process synchronously and return response."""
        return self._process(request)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while self._running:
            try:
                request, callback = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            response = self._process(request)
            try:
                callback(response)
            except Exception as exc:
                log.error("[%s] callback raised: %s", self.name, exc)
            self._queue.task_done()

    def _process(self, request: ClientRequest) -> ClientResponse:
        log.info(
            "[%s] processing %s  task=%r", self.name, request.request_id[:8], request.task
        )
        try:
            result = self._execute_task(request.task, request.payload)
        except Exception as exc:
            log.error("[%s] task failed: %s", self.name, exc)
            return ClientResponse(
                request_id=request.request_id,
                agent_name=self.name,
                result=None,
                consensus_reached=False,
                votes={},
                block_number=self.nodes[0].block_number,
                storage_info={},
                error=str(exc),
            )

        # Run consensus (may be skipped in subclasses — e.g. Baseline)
        consensus_result = self._run_consensus(request.task, result)

        # Store result according to the model's strategy
        storage_info = self._store_result(request, result, consensus_result)

        block_number = self.nodes[0].block_number
        response = ClientResponse(
            request_id=request.request_id,
            agent_name=self.name,
            result=result,
            consensus_reached=consensus_result.get("consensus_reached", False),
            votes=consensus_result.get("votes", {}),
            block_number=block_number,
            storage_info=storage_info,
        )
        log.info(
            "[%s] -> %s  block=#%d  consensus=%s  storage=%s",
            self.name,
            request.request_id[:8],
            block_number,
            response.consensus_reached,
            storage_info.get("mode", "none"),
        )
        return response

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def _run_consensus(self, task: str, result: Any) -> dict[str, Any]:
        """Run internal consensus among nodes. Override to skip or modify."""
        return self._consensus.run(task=task, proposed_result=result)

    def _store_result(
        self,
        request: ClientRequest,
        result: Any,
        consensus_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Persist the result after consensus.
        Override in subclasses to implement baseline / hash / full strategy.
        Returns a storage_info dict included in the ClientResponse.
        """
        return {"mode": "none"}

    def _execute_task(self, task: str, payload: Any) -> Any:
        if self._task_handler is not None:
            return self._task_handler(task, payload)
        return {"echo": payload, "agent": self.name, "processed_at": time.time()}

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "agent": self.name,
            "model": self.__class__.__name__,
            "running": self._running,
            "node_count": len(self.nodes),
            "queue_size": self._queue.qsize(),
            "nodes": [
                {"id": n.node_id, "block": n.block_number, "root": n.state_root[:12]}
                for n in self.nodes
            ],
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, nodes={len(self.nodes)})"
