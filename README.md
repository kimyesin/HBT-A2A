# HBT-A2A: Hybrid Blockchain-Based Trustworthy Agent-To-Agent Protocol

Based on ethereum/py-evm (MIT License)
Extended with a hybrid blockchain agent framework for trustworthy A2A communication.

---

## Overview

This repository implements **HBT-A2A**, a lightweight hash-based on/off-chain verification scheme for trustworthy communication in A2A (Agent-to-Agent) based multi-agent systems.

By storing only minimal verification data (hash values + metadata) on-chain and keeping large-scale log data off-chain, HBT-A2A reduces processing overhead while improving system scalability.

This repository documents the ongoing research based on the following two papers.

---

## Paper 1: HBT-A2A (ASK 2026)

> **"HBT-A2A: A Lightweight Hybrid Blockchain-Based Trustworthy Agent-To-Agent Protocol"**
> Ye-Sin Kim, Chae-Yeon Park, Il-Gu Lee — Dept. of Convergence Security Engineering, Sungshin Women's University, ASK 2026

### Model Comparison

| Technique  | Verification | Storage      |
|------------|--------------|--------------|
| Baseline   | None         | Off-chain    |
| Full-chain | On-chain     | On-chain     |
| HBT-A2A    | Hash-based   | On/Off-chain |

### How It Works

```
① Event generation       — Each agent generates log data (input, result, state)
② Off-chain storage      — Large-scale log data is stored in an off-chain database
③ Hash generation        — SHA-256 hash is computed from the off-chain data
④ On-chain recording     — Only the hash + minimal metadata is written on-chain
⑤ Hash comparison        — Recomputed hash from off-chain is compared to on-chain hash
⑥ Consensus process      — Nodes reach majority-vote based consensus
⑦ Malicious detection    — Nodes with abnormal patterns are flagged as malicious
```

### Key Results

Under attack frequency ≥ 4,000 attacks/sec (vs. Baseline / Full-chain):
- 3.2× higher throughput compared to Baseline
- 35% lower loss rate compared to Baseline
- 78.7% lower loss rate compared to Full-chain

---

## Paper 2: Trustworthy A2A (KIISC Summer Conference 2026)

> **"Trustworthy A2A: A Multi-Replica Hybrid Blockchain Framework for Secure Multi-Agent Systems"**
> Ye-Sin Kim, Chae-Yeon Park, Il-Gu Lee — Dept. of Convergence Security Engineering, Sungshin Women's University

This follow-up study addresses a key limitation of HBT-A2A's single off-chain DB design: when the off-chain DB is corrupted or an on/off-chain communication failure occurs, data integrity becomes difficult to verify. Trustworthy A2A extends the architecture to a **multi-replica off-chain DB (3 replicas)** with majority-based hash verification.

### Model Comparison

| Technique       | Verification                      | Storage Structure          |
|------------------|------------------------------------|------------------------------|
| HBT-A2A          | Hash-based                         | Single off-chain DB           |
| Trustworthy A2A  | Majority-based hash verification   | Multi-replica off-chain DB    |

### How It Works

```
① Event generation              — Multiple agents (Agent A, B, ...) generate events/log data
② Off-chain data storage         — The same log data is replicated across off-chain DB1–DB3
③ Hash generation                — A hash (h1, h2, h3) is computed for each DB's stored data
④ On-chain metadata recording    — Hash values + metadata are recorded on-chain
⑤ Majority-based verification    — Each DB hash is compared to the on-chain hash;
                                     data is trusted if 2 of 3 DBs match
⑥ Recovery of inconsistent DB    — A mismatched DB is resynchronized from a trusted DB
⑦ Consensus process              — Nodes reach consensus based on metadata + verification results
```

### Key Results (at 10,000 attacks)

| Metric | HBT-A2A | Trustworthy A2A |
|---|---|---|
| Verification success rate (Performance) | 45.4% | **100%** |
| Verification complexity (operation count) | 161,243 | 129,876 (1.24× lower) |
| Verification efficiency | 1.0× | **3.0× higher** |

---

## Repository Structure

```
eth/agents/
├── agent.py          # Base Agent inherited by all models (queue handling, consensus call, response)
├── consensus.py       # Majority-vote consensus among AgentNodes (AgentConsensus)
├── node.py            # Individual consensus participant (AgentNode)
├── onchain.py         # On-chain store — append-only hash chain (OnChainStore, Block)
├── offchain.py        # Off-chain store — fast in-memory storage (OffChainStore)
├── request.py         # Client request/response data structures (ClientRequest, ClientResponse)
└── models/
    ├── baseline.py    # Baseline: no consensus, off-chain only
    ├── hash_model.py  # HBT-A2A: hash on-chain + full data off-chain
    └── full_model.py  # Full-chain: all data on-chain

demo_agents.py         # Demo comparing all 3 models
benchmark.py           # Throughput benchmark
attack_benchmark.py    # Attack environment benchmark
```

> The current code implements the architecture of Paper 1 (HBT-A2A: single off-chain DB + hash-based verification).

---

## Roadmap

Building on the Trustworthy A2A paper's architecture, the implementation will be extended in the following directions:

- **Off-chain DB count optimization**: analyze the trade-off between verification success rate, complexity, and efficiency for different DB counts (e.g. 2 / 3 / 5 replicas), based on the proposed 3-replica structure
- **Majority-based verification model**: extend `offchain.py` to a multi-DB structure and add majority-based hash comparison against the on-chain hash
- **DB recovery logic**: design a `recovery` module that resynchronizes a mismatched DB from a trusted DB
- **Extended malicious agent detection**: leverage verification result patterns across multiple DBs to identify abnormal agents
- **Retry policy optimization**: compare performance across combinations of DB count and retry limit, based on the current "up to 10 retries" policy

---

## Experimental Setup

- Python 3.11.9
- EVM-based open-source library: py-evm
- Network modeling: probabilistic collisions + up to 3 retransmissions

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

## License

MIT License — follows the original ethereum/py-evm license.