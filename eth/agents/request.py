"""
Client request/response data structures.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ClientRequest:
    task: str
    payload: Any = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return f"ClientRequest(id={self.request_id[:8]}, task={self.task!r})"


@dataclass
class ClientResponse:
    request_id: str
    agent_name: str
    result: Any
    consensus_reached: bool
    votes: dict[str, Any]          # node_id → vote cast
    block_number: int
    storage_info: dict[str, Any]   # where/how data was stored
    completed_at: float = field(default_factory=time.time)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None

    def __repr__(self) -> str:
        status = "OK" if self.success else f"ERR:{self.error}"
        mode = self.storage_info.get("mode", "?")
        return (
            f"ClientResponse(req={self.request_id[:8]}, "
            f"agent={self.agent_name}, status={status}, "
            f"consensus={self.consensus_reached}, storage={mode})"
        )
