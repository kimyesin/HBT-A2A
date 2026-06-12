# HBT-A2A: A Lightweight Hybrid Blockchain-Based Trustworthy Agent-To-Agent Protocol

> **Based on [ethereum/py-evm](https://github.com/ethereum/py-evm)** (MIT License)  
> Extended with a hybrid blockchain agent framework for trustworthy A2A communication.

## Overview

This repository implements **HBT-A2A**, a lightweight distributed verification scheme for trustworthy communication in A2A-based multi-agent systems.

By storing only minimal verification data (hash values and metadata) on-chain and keeping large-scale data off-chain, HBT-A2A reduces processing overhead while improving system scalability.

> This code is the experimental implementation for the following paper:  
> **"HBT-A2A: A Lightweight Hybrid Blockchain-Based Trustworthy Agent-To-Agent Protocol"**  
> Ye-Sin Kim, Chae-Yeon Park, Il-Gu Lee — Dept. of Convergence Security Engineering, Sungshin Women's University, ASK 2026

---

## Model Comparison

| Technique | Verification | Storage |
|---|---|---|
| Baseline | None | Off-chain |
| Full-chain | On-chain | On-chain |
| **HBT-A2A** | **Hash-based** | **On/Off-chain** |

---

## How It Works

```
① Event generation       — Each agent generates log data (input, result, state)
② Off-chain storage      — Large-scale log data is stored in an off-chain database
③ Hash generation        — SHA-256 hash is computed from the off-chain data
④ On-chain recording     — Only the hash + minimal metadata is written on-chain
⑤ Hash comparison        — Recomputed hash from off-chain is compared to on-chain hash
⑥ Consensus process      — Nodes reach majority-vote based consensus
⑦ Malicious detection    — Nodes with abnormal patterns are flagged as malicious
```

---

## Experimental Setup

- Python 3.11.9
- EVM-based open-source library: [py-evm](https://github.com/ethereum/py-evm)
- Network modeling: probabilistic collisions + up to 3 retransmissions

---

## Key Results

Under attack frequency ≥ 4,000 attacks/sec:

- **3.2× higher throughput** compared to Baseline
- **35% lower loss rate** compared to Baseline
- **78.7% lower loss rate** compared to Full-chain

---

## Repository Structure

```
eth/agents/
├── agent.py          # Base agent (shared logic)
├── consensus.py      # Majority-vote consensus
├── node.py           # Individual consensus node
├── onchain.py        # On-chain store (append-only, immutable)
├── offchain.py       # Off-chain store (fast, overwritable)
├── request.py        # Client request/response
└── models/
    ├── baseline.py   # Baseline: no consensus, off-chain only
    ├── hash_model.py # HBT-A2A: hash on-chain + full data off-chain
    └── full_model.py # Full-chain: all data on-chain

demo_agents.py        # Demo comparing all 3 models
benchmark.py          # Throughput benchmark
attack_benchmark.py   # Attack environment benchmark
```

---

## Getting Started

```bash
# Clone the repository
git clone https://github.com/kimyesin/HBT-A2A.git
cd HBT-A2A

# Install dependencies
pip install -e .

# Run demo (compare all 3 models)
python demo_agents.py

# Run benchmarks
python benchmark.py
python attack_benchmark.py
```

---

## License

MIT License — follows the original [ethereum/py-evm](https://github.com/ethereum/py-evm) license.