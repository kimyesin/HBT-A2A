# run_experiment.py
"""
Interactive experiment runner for HBT-A2A / Trustworthy A2A.

Run this script and answer the prompts to choose:
  - x-axis     : attack intensity or attack frequency
  - y-axis     : performance / complexity / efficiency (one or more)
  - models     : which agent models to compare
  - attackers  : which attacker types to apply (1: on-chain, 2: single
                 off-chain, 3: multi off-chain)
  - repeats    : number of repetitions per x-value (averaged)

Produces a CSV of results and a matplotlib PNG chart per selected y-axis.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eth.agents.models.off_chain_baseline_model import BaselineAgent
from eth.agents.models.full_chain_model import FullChainAgent
from eth.agents.models.hbt_a2a_model import HBTA2AAgent
from eth.agents.models.trustworthy_a2a_model import TrustworthyA2AAgent
from eth.agents.request import ClientRequest
from eth.agents import attacks


# ----------------------------------------------------------------------
# Model registry
# ----------------------------------------------------------------------

MODEL_REGISTRY: dict[str, Callable[[], Any]] = {
    "1": ("Baseline", lambda: BaselineAgent("Agent-A", node_count=3)),
    "2": ("FullChain", lambda: FullChainAgent("Agent-A", node_count=3)),
    "3": ("HBT-A2A", lambda: HBTA2AAgent("Agent-A", node_count=3)),
    "4": ("Trustworthy", lambda: TrustworthyA2AAgent("Agent-A", node_count=3, db_count=3)),
}

ATTACKER_REGISTRY = {
    "1": "onchain",
    "2": "offchain_single",
    "3": "offchain_multi",
}


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
    """Apply the selected attacker type(s) to the agent's storage."""
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


def verify_request(agent: Any, request_id: str) -> tuple[bool, int]:
    """
    Verify a single request and return (verified, complexity).

    Complexity definition:
      - HBT-A2A      : 1 hash recompute + 1 compare            = 2
      - Trustworthy  : db_count hashes + db_count compares
                       + 1 majority decision (+ recovery writes) = 2*db_count + 1 (+recovered)
      - Baseline     : no verification possible                  = 0  (always "unverified")
      - FullChain    : 1 on-chain compare                        = 1  (always verified)
    """
    cls_name = agent.__class__.__name__

    if cls_name == "HBTA2AAgent":
        verified = agent.verify(request_id)
        return verified, 2

    if cls_name == "TrustworthyA2AAgent":
        result = agent.verify_with_recovery(request_id)
        db_count = agent.offchain._db_count
        complexity = 2 * db_count + 1
        if result["recovery_attempted"]:
            complexity += len(result["recovery_result"]["recovered_indices"])
        return result["verified"], complexity

    if cls_name == "FullChainAgent":
        # On-chain data is always authoritative -> always verified
        return True, 1

    if cls_name == "BaselineAgent":
        # No verification mechanism exists
        return False, 0

    return False, 0


# ----------------------------------------------------------------------
# Single experiment run
# ----------------------------------------------------------------------

def run_once(
    model_name: str,
    n_requests: int,
    attacker_types: list[str],
    attack_count: int,
    intensity_kb: float,
) -> dict[str, float]:
    """
    Run one experiment instance:
      1. Process n_requests requests through the agent.
      2. Apply `attack_count` attacks (each of intensity_kb).
      3. Verify all requests and compute Performance / Complexity / Efficiency.
    """
    factory = next(f for label, f in MODEL_REGISTRY.values() if label == model_name)
    agent = factory()

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
    model_name: str,
    n_requests: int,
    attacker_types: list[str],
    attack_count: int,
    intensity_kb: float,
    repeats: int,
) -> dict[str, float]:
    """Run `repeats` times and return averaged metrics."""
    totals = {"performance": 0.0, "complexity": 0.0, "efficiency": 0.0}
    for _ in range(repeats):
        result = run_once(model_name, n_requests, attacker_types, attack_count, intensity_kb)
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

    x_axis_choices = {"1": "공격 강도 (intensity_kb)", "2": "공격 빈도 (attack_count)"}
    x_axis_key = ask("1. x축을 선택하세요:", x_axis_choices)[0]

    y_axis_choices = {"1": "Performance", "2": "Complexity", "3": "Efficiency"}
    y_axis_keys = ask("\n2. y축을 선택하세요 (복수 선택 가능):", y_axis_choices, multi=True)

    model_choices = {k: v[0] for k, v in MODEL_REGISTRY.items()}
    model_keys = ask("\n3. 비교할 모델을 선택하세요 (복수 선택 가능):", model_choices, multi=True)

    attacker_choices = {
        "1": "온체인 공격",
        "2": "단일 오프체인 공격 (DB1)",
        "3": "다중 오프체인 공격 (DB1~3 랜덤)",
    }
    attacker_keys = ask("\n4. 공격 모델을 선택하세요 (복수 선택 가능):", attacker_choices, multi=True)
    attacker_types = [ATTACKER_REGISTRY[k] for k in attacker_keys]

    repeats = int(input("\n5. 실험 반복 횟수: ").strip() or "1")
    n_requests = int(input("6. 요청(레코드) 개수: ").strip() or "100")

    if x_axis_key == "1":
        # attack intensity varies; attack_count fixed
        fixed_attack_count = int(input("7. 공격 빈도(고정값, 공격 횟수): ").strip() or "5")
        x_label = "Attack intensity (KB)"
        x_values_raw = input("8. x축 값들 (예: 0,1,2,3,4,5): ").strip()
        x_values = [float(v) for v in x_values_raw.split(",")]
    else:
        # attack count varies; intensity fixed
        fixed_intensity = float(input("7. 공격 강도(고정값, KB): ").strip() or "1.0")
        x_label = "Attack count"
        x_values_raw = input("8. x축 값들 (예: 0,2,5,10,20,50,100): ").strip()
        x_values = [int(v) for v in x_values_raw.split(",")]

    # ------------------------------------------------------------------
    # Run experiments
    # ------------------------------------------------------------------
    model_names = [MODEL_REGISTRY[k][0] for k in model_keys]
    y_labels = [y_axis_choices[k] for k in y_axis_keys]

    all_results: dict[str, dict[float, dict[str, float]]] = {m: {} for m in model_names}

    for model_name in model_names:
        for x in x_values:
            if x_axis_key == "1":
                intensity_kb = x
                attack_count = fixed_attack_count
            else:
                intensity_kb = fixed_intensity
                attack_count = int(x)

            result = run_repeated(
                model_name, n_requests, attacker_types, attack_count, intensity_kb, repeats
            )
            all_results[model_name][x] = result
            print(f"[{model_name}] x={x} -> {result}")

    # ------------------------------------------------------------------
    # Save CSV
    # ------------------------------------------------------------------
    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / "experiment_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["model", "x", "performance", "complexity", "efficiency"])
        for model_name, x_map in all_results.items():
            for x, metrics in x_map.items():
                writer.writerow([model_name, x, metrics["performance"], metrics["complexity"], metrics["efficiency"]])
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
        plt.figure(figsize=(7, 5))
        for model_name, x_map in all_results.items():
            xs = sorted(x_map.keys())
            ys = [x_map[x][metric] for x in xs]
            plt.plot(xs, ys, marker="o", label=model_name)
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