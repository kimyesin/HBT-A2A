# eth/agents/multi_offchain.py
"""
MultiOffChainStore — 다중 복제 오프체인 저장소.

특성:
  - 내부적으로 db_count 개의 독립적인 OffChainStore 인스턴스를 유지
  - 모든 DB에 동일한 레코드를 완전 복제하여 저장
  - 과반수(majority) 검증을 통해 변조된 DB를 탐지하고 복구
  - 특정 DB를 차단(block)하여 연결 두절 시나리오를 시뮬레이션
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from eth.agents.offchain import OffChainStore

log = logging.getLogger(__name__)


def _sha256_record(record: dict[str, Any]) -> str:
    raw = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class MultiOffChainStore:
    """
    다중 복제 오프체인 저장소 (MR-HBT-A2A용).

    Security model
    --------------
    Read  : 과반수 검증을 통해 변조된 DB를 탐지 가능.
    Write : 모든 DB에 동시 복제 — 단일 DB 변조 시 과반수 검증으로 탐지.
    """

    def __init__(self, db_count: int = 3) -> None:
        self._db_count = db_count
        self._stores: list[OffChainStore] = [OffChainStore() for _ in range(db_count)]
        self._blocked: set[int] = set()

        log.info("[MultiOffChainStore] %d개의 DB 인스턴스 초기화 완료.", db_count)

    # ------------------------------------------------------------------ #
    # Write                                                                #
    # ------------------------------------------------------------------ #

    def save(self, key: str, record: dict[str, Any]) -> None:
        """모든 내부 OffChainStore 인스턴스에 레코드를 완전 복제 저장."""
        for i, store in enumerate(self._stores):
            store.save(key, record)
            log.debug("[MultiOffChainStore] DB[%d]에 키 %r 저장 완료.", i, key)

    # ------------------------------------------------------------------ #
    # Read                                                                 #
    # ------------------------------------------------------------------ #

    def get(self, key: str, db_index: int = 0) -> Optional[dict[str, Any]]:
        """
        지정된 DB 인덱스에서 레코드를 반환.
        해당 DB가 차단(blocked) 상태이면 None을 반환.
        """
        if db_index in self._blocked:
            log.debug("[MultiOffChainStore] DB[%d]는 차단 상태 — None 반환.", db_index)
            return None
        return self._stores[db_index].get(key)

    def get_all_copies(self, key: str) -> list[Optional[dict[str, Any]]]:
        """모든 DB에서 레코드를 조회하여 리스트로 반환 (차단된 DB는 None)."""
        return [self.get(key, i) for i in range(self._db_count)]

    # ------------------------------------------------------------------ #
    # Majority verification                                                #
    # ------------------------------------------------------------------ #

    def majority_verify(self, key: str, onchain_hash: str) -> dict[str, Any]:
        """
        각 DB의 레코드 해시를 온체인 해시와 비교하여 과반수 검증을 수행.

        Returns
        -------
        {
            "valid"          : bool,        # 과반수(db_count//2 + 1) 이상 일치 여부
            "match_count"    : int,
            "total_count"    : int,
            "bad_db_indices" : list[int]    # 해시 불일치 DB 인덱스 목록
        }
        """
        threshold = self._db_count // 2 + 1
        match_count = 0
        bad_db_indices: list[int] = []

        for i in range(self._db_count):
            record = self.get(key, i)
            if record is None:
                bad_db_indices.append(i)
                log.debug("[MultiOffChainStore] DB[%d] 키 %r: 레코드 없음(차단 또는 미존재).", i, key)
                continue

            record_hash = _sha256_record(record)
            if record_hash == onchain_hash:
                match_count += 1
                log.debug("[MultiOffChainStore] DB[%d] 키 %r: 해시 일치.", i, key)
            else:
                bad_db_indices.append(i)
                log.debug(
                    "[MultiOffChainStore] DB[%d] 키 %r: 해시 불일치 (expected=%s, got=%s).",
                    i, key, onchain_hash[:16], record_hash[:16],
                )

        valid = match_count >= threshold
        log.info(
            "[MultiOffChainStore] majority_verify 키=%r: %d/%d 일치, 결과=%s.",
            key, match_count, self._db_count, "VALID" if valid else "INVALID",
        )
        return {
            "valid": valid,
            "match_count": match_count,
            "total_count": self._db_count,
            "bad_db_indices": bad_db_indices,
        }

    # ------------------------------------------------------------------ #
    # Recovery                                                             #
    # ------------------------------------------------------------------ #

    def recover(self, key: str) -> dict[str, Any]:
        """
        과반수가 일치하는 레코드를 기준으로 불량 DB를 복구.

        동작:
          1. 각 DB의 해시 빈도를 집계하여 과반수 해시를 식별
          2. 과반수 해시를 가진 DB 중 첫 번째를 소스로 선택
          3. 불량 DB(해시 불일치 또는 레코드 없음)에 소스 레코드를 덮어씀

        Returns
        -------
        {
            "recovered"          : bool,
            "recovered_indices"  : list[int],
            "source_index"       : int          (-1이면 복구 불가)
        }
        """
        hash_to_indices: dict[str, list[int]] = {}

        for i in range(self._db_count):
            record = self.get(key, i)
            if record is None:
                continue
            h = _sha256_record(record)
            hash_to_indices.setdefault(h, []).append(i)

        if not hash_to_indices:
            log.warning("[MultiOffChainStore] recover 키=%r: 유효한 DB가 없어 복구 불가.", key)
            return {"recovered": False, "recovered_indices": [], "source_index": -1}

        # 가장 빈도가 높은 해시 선택 (과반수)
        majority_hash = max(hash_to_indices, key=lambda h: len(hash_to_indices[h]))
        majority_indices = hash_to_indices[majority_hash]
        source_index = majority_indices[0]
        source_record = self._stores[source_index].get(key)

        # 불량 인덱스: 과반수 그룹에 속하지 않는 DB
        all_indices = set(range(self._db_count))
        majority_set = set(majority_indices)
        bad_indices = [i for i in all_indices if i not in majority_set]

        recovered_indices: list[int] = []
        for i in bad_indices:
            if source_record is not None:
                self._stores[i].save(key, source_record)
                recovered_indices.append(i)
                log.info(
                    "[MultiOffChainStore] DB[%d] 키=%r: DB[%d]로부터 복구 완료.",
                    i, key, source_index,
                )

        return {
            "recovered": len(recovered_indices) > 0,
            "recovered_indices": recovered_indices,
            "source_index": source_index,
        }

    # ------------------------------------------------------------------ #
    # Attack / Fault simulation                                            #
    # ------------------------------------------------------------------ #

    def block_db(self, db_index: int) -> None:
        """지정된 DB를 차단 상태로 설정 (연결 두절 시뮬레이션)."""
        self._blocked.add(db_index)
        log.info("[MultiOffChainStore] DB[%d] 차단됨.", db_index)

    def unblock_db(self, db_index: int) -> None:
        """지정된 DB의 차단을 해제."""
        self._blocked.discard(db_index)
        log.info("[MultiOffChainStore] DB[%d] 차단 해제됨.", db_index)

    def corrupt_db(self, db_index: int, key: str, forged_data: dict[str, Any]) -> bool:
        """
        지정된 DB의 특정 키를 위조 데이터로 덮어씀 (공격 시뮬레이션).
        Returns True if the key existed and was overwritten.
        """
        result = self._stores[db_index].overwrite_attack(key, forged_data)
        if result:
            log.warning(
                "[MultiOffChainStore] DB[%d] 키=%r: 변조 공격 성공.", db_index, key
            )
        return result

    # ------------------------------------------------------------------ #
    # Inspection                                                           #
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        """DB[0]을 기준으로 전체 레코드 수를 반환."""
        return len(self._stores[0])

    def __repr__(self) -> str:
        return (
            f"MultiOffChainStore("
            f"db_count={self._db_count}, "
            f"records={len(self)}, "
            f"blocked={sorted(self._blocked)})"
        )
