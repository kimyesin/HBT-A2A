# run_experiment.py
"""
Interactive experiment runner for HBT-A2A / Trustworthy A2A.

Run this script and answer the prompts to choose:
  - x-axis     : attack intensity or attack frequency
  - y-axis     : performance / complexity / efficiency (one or more)
  - N values   : which DB counts to compare (each N = one line on the graph)
                 N=0 → FullChain, N=1 → HBT-A2A, N≥2 → Trustworthy(db_count=N)
  - attackers  : which attacker types to apply
  - repeats    : number of repetitions per x-value (averaged)

Produces a CSV of results and a matplotlib PNG chart per selected y-axis.
"""
from __future__ import annotations

import csv
import sys
import types
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_eth_pkg = types.ModuleType("eth")
_eth_pkg.__path__ = [str(ROOT / "eth")]
sys.modules["eth"] = _eth_pkg

from eth.agents.models.off_chain_baseline_model import BaselineAgent
from eth.agents.models.full_chain_model import FullChainAgent
from eth.agents.models.hbt_a2a_model import HBTA2AAgent
from eth.agents.models.trustworthy_a2a_model import TrustworthyA2AAgent
from eth.agents.request import ClientRequest
import eth.agents.attacks as attacks


# ----------------------------------------------------------------------
# DB 개수 N에 따른 에이전트 생성
# ----------------------------------------------------------------------

def make_agent(n: int) -> Any:
    """
    N=0 → FullChainAgent
    N=1 → HBTA2AAgent
    N≥2 → TrustworthyA2AAgent(db_count=N)
    """
    if n == 0:
        return FullChainAgent("Agent-A", node_count=3)
    elif n == 1:
        return HBTA2AAgent("Agent-A", node_count=3)
    else:
        return TrustworthyA2AAgent("Agent-A", node_count=3, db_count=n)


def label_for_n(n: int) -> str:
    if n == 0:
        return "N=0 (FullChain)"
    elif n == 1:
        return "N=1 (HBT-A2A)"
    else:
        return f"N={n} (Trustworthy)"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def make_payload(i: int) -> dict[str, Any]:
    return {
        "sender": "agent-A",
        "message": f"task #{i} " + "content " * 5,
        "metadata": {"timestamp": 1234567890.0 + i},
    }


def apply_attack(agent: Any, attacker_types: list[str], intensity_kb: float) -> None:
    for atype in attacker_types:
        if atype == "onchain":
            if hasattr(agent, "onchain"):
                attacks.attack_onchain(agent.onchain, intensity_kb)
        elif atype == "offchain_single":
            if hasattr(agent, "offchain") and hasattr(agent.offchain, "_store"):
                attacks.attack_offchain(agent.offchain, intensity_kb)
        elif atype == "offchain_multi":
            if hasattr(agent, "offchain") and hasattr(agent.offchain, "_stores"):
                attacks.attack_multi_offchain(agent.offchain, intensity_kb)
            elif hasattr(agent, "offchain") and hasattr(agent.offchain, "_store"):
                attacks.attack_offchain(agent.offchain, intensity_kb)


def verify_request(agent: Any, request_id: str) -> tuple[bool, int]:
    cls_name = agent.__class__.__name__

    if cls_name == "HBTA2AAgent":
        verified = agent.verify(request_id)
        return verified, 2

    if cls_name == "TrustworthyA2AAgent":
        result = agent.verify_with_recovery(request_id)
        db_count = agent.offchain._db_count
        complexity = 2 * db_count + 1
        if result["recovery_attempted"] and result["recovery_result"]:
            recovered = result["recovery_result"].get("recovered_indices", [])
            complexity += len(recovered)
        return result["verified"], complexity

    if cls_name == "FullChainAgent":
        return True, 1

    if cls_name == "BaselineAgent":
        return False, 0

    return False, 0


# ----------------------------------------------------------------------
# Experiment runner
# ----------------------------------------------------------------------

def run_once(
    n: int,
    n_requests: int,
    attacker_types: list[str],
    attack_count: int,
    intensity_kb: float,
) -> dict[str, float]:
    agent = make_agent(n)

    req_ids = []
    for i in range(n_requests):
        resp = agent.handle(ClientRequest(task="echo", payload=make_payload(i)))
        req_ids.append(resp.request_id)

    for _ in range(attack_count):
        apply_attack(agent, attacker_types, intensity_kb)

    success = 0
    total_complexity = 0
    for rid in req_ids:
        verified, complexity = verify_request(agent, rid)
        total_complexity += complexity
        if verified:
            success += 1

    performance = success / n_requests * 100 if n_requests else 0.0
    efficiency = (performance / total_complexity) if total_complexity else 0.0

    return {
        "performance": performance,
        "complexity": total_complexity,
        "efficiency": efficiency,
    }


def run_repeated(
    n: int,
    n_requests: int,
    attacker_types: list[str],
    attack_count: int,
    intensity_kb: float,
    repeats: int,
) -> dict[str, float]:
    totals = {"performance": 0.0, "complexity": 0.0, "efficiency": 0.0}
    for _ in range(repeats):
        result = run_once(n, n_requests, attacker_types, attack_count, intensity_kb)
        for k in totals:
            totals[k] += result[k]
    return {k: v / repeats for k, v in totals.items()}


# ----------------------------------------------------------------------
# Interactive prompts
# ----------------------------------------------------------------------

def ask(prompt: str, choices: dict[str, str], multi: bool = False) -> list[str]:
    print(prompt)
    for key, label in choices.items():
        print(f"  {key}) {label}")
    raw = input("선택 (예: 1 또는 1,3): ").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not multi and len(keys) > 1:
        keys = keys[:1]
    for k in keys:
        if k not in choices:
            raise ValueError(f"잘못된 선택: {k}")
    return keys


def main() -> None:
    print("=== HBT-A2A / Trustworthy A2A 실험 설정 ===\n")

    x_axis_choices = {
        "1": "공격 강도 (intensity_kb)",
        "2": "공격 빈도 (attack_count)",
    }
    x_axis_key = ask("1. x축을 선택하세요:", x_axis_choices)[0]

    y_axis_choices = {"1": "Performance", "2": "Complexity", "3": "Efficiency"}
    y_axis_keys = ask("\n2. y축을 선택하세요 (복수 선택 가능):", y_axis_choices, multi=True)

    n_values_raw = input("\n3. 비교할 DB 개수 N 값들을 입력하세요 (예: 0,1,2,3,5,7,10): ").strip()
    n_values = [int(v) for v in n_values_raw.split(",")]

    attacker_choices = {
        "1": "온체인 공격",
        "2": "단일 오프체인 공격 (DB1)",
        "3": "다중 오프체인 공격 (강도에 따라 여러 DB 동시 공격)",
    }
    attacker_keys = ask("\n4. 공격 모델을 선택하세요 (복수 선택 가능):", attacker_choices, multi=True)
    attacker_types = [{"1": "onchain", "2": "offchain_single", "3": "offchain_multi"}[k] for k in attacker_keys]

    repeats = int(input("\n5. 실험 반복 횟수: ").strip() or "1")
    n_requests = int(input("6. 요청(레코드) 개수: ").strip() or "100")

    if x_axis_key == "1":
        fixed_attack_count = int(input("7. 공격 빈도(고정값, 공격 횟수): ").strip() or "5")
        x_label = "Attack intensity (KB)"
        x_values_raw = input("8. x축 값들 (예: 0,10,20,30,50,70,100): ").strip()
        x_values: list[Any] = [float(v) for v in x_values_raw.split(",")]
    else:
        fixed_intensity = float(input("7. 공격 강도(고정값, KB): ").strip() or "10.0")
        x_label = "Attack count"
        x_values_raw = input("8. x축 값들 (예: 0,10,20,30,50,70,100): ").strip()
        x_values = [int(v) for v in x_values_raw.split(",")]

    # ------------------------------------------------------------------
    # Run experiments: N별 × x값별
    # ------------------------------------------------------------------
    y_labels = [y_axis_choices[k] for k in y_axis_keys]
    all_results: dict[str, dict[Any, dict[str, float]]] = {label_for_n(n): {} for n in n_values}

    for n in n_values:
        label = label_for_n(n)
        for x in x_values:
            if x_axis_key == "1":
                intensity_kb = float(x)
                attack_count = fixed_attack_count
            else:
                intensity_kb = fixed_intensity
                attack_count = int(x)

            result = run_repeated(n, n_requests, attacker_types, attack_count, intensity_kb, repeats)
            all_results[label][x] = result
            print(f"[{label}] x={x} -> {result}")

    # ------------------------------------------------------------------
    # Save CSV
    # ------------------------------------------------------------------
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / "experiment_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "x", "performance", "complexity", "efficiency"])
        for label, x_map in all_results.items():
            for x, metrics in x_map.items():
                writer.writerow([label, x, metrics["performance"], metrics["complexity"], metrics["efficiency"]])
    print(f"\nCSV saved to {csv_path}")

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib이 설치되어 있지 않아 그래프를 생성하지 않습니다.")
        return

    metric_keys = {"Performance": "performance", "Complexity": "complexity", "Efficiency": "efficiency"}

    for y_label in y_labels:
        metric = metric_keys[y_label]
        plt.figure(figsize=(8, 5))
        for label, x_map in all_results.items():
            xs = sorted(x_map.keys())
            ys = [x_map[x][metric] for x in xs]
            plt.plot(xs, ys, marker="o", label=label)
        plt.xlabel(x_label)
        plt.ylabel(y_label)
        plt.title(f"{y_label} vs {x_label}")
        plt.legend()
        plt.grid(True, alpha=0.3)
        out_path = out_dir / f"{metric}.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Chart saved to {out_path}")


if __name__ == "__main__":
    main()