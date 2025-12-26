# SWE-RL: Self-Play Software Engineering with Reinforcement Learning

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![arXiv](https://img.shields.io/badge/arXiv-2512.18552-b31b1b.svg)](https://arxiv.org/abs/2512.18552)

An implementation of **Self-play SWE-RL (SSR)** - where AI agents create their own software engineering training tasks and learn to solve them.

---

## 🙏 Based on Groundbreaking Research

This project implements concepts from:

> **"SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution"**
>
> **Yuxiang Wei, Olivier Duchenne, Jade Copet, Quentin Carbonneaux, Lingming Zhang, Daniel Fried, Gabriel Synnaeve, Rishabh Singh, Sida I. Wang**
>
> Meta AI (FAIR) • University of Illinois Urbana-Champaign • Carnegie Mellon University
>
> 📄 [Read the paper](https://arxiv.org/abs/2512.18552)

We are deeply grateful to the research team for publishing this innovative work that demonstrates how reinforcement learning on real-world software evolution data can advance LLM reasoning capabilities.

---

## 🎯 What is SSR?

**Self-play SWE-RL** is a paradigm where:

1. An **Injector Agent** creates realistic bugs in working code
2. A **Validator** ensures the bugs are meaningful and solvable
3. A **Solver Agent** attempts to fix the bugs using only test feedback
4. Both agents improve through this self-play loop

```
     ┌─────────────┐
     │   Inject    │ ──── Creates bug + oracle test
     │    Agent    │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │  Validate   │ ──── 7-step verification
     │  (7 steps)  │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │   Solver    │ ──── Fixes bug using test only
     │    Agent    │
     └──────┬──────┘
            │
            ▼
     ┌─────────────┐
     │   Reward    │ ──── +1.0 if solved, 0.0 otherwise
     └─────────────┘
```

---

## 📁 Repository Structure

```
├── ssr-studio/          # Main implementation
│   ├── demo.py          # Run a complete episode
│   ├── examples/        # Sample project for testing
│   ├── src/             # Python backend
│   └── ui/              # Next.js dashboard
├── CONTRIBUTING.md
├── LICENSE
└── README.md            # You are here
```

---

## 🚀 Quick Start

```bash
cd ssr-studio
pip install openai anthropic rich pytest

# Run the demo (requires API key)
python demo.py --api-key YOUR_OPENAI_KEY
```

See [ssr-studio/README.md](ssr-studio/README.md) for full documentation.

---

## 🔬 Key Innovation: 7-Step Validation

The SSR paper introduces rigorous validation for generated bugs:

| Step | Validation |
|------|------------|
| 1 | Test file exists |
| 2 | Code parses correctly |
| 3 | Original tests still pass |
| 4 | Bug is in allowed scope |
| 5 | Oracle test fails on buggy code |
| 6 | Oracle test passes on clean code |
| 7 | Inverse mutation testing |

This ensures every generated training example is meaningful.

---

## 📊 Research Applications

- **Training data generation** - Create unlimited bug/fix pairs
- **Model evaluation** - Compare LLM fixing capabilities  
- **Self-improvement** - Enable agents to generate their own curriculum
- **Benchmark creation** - Generate SWE-bench-style tasks

---

## 📄 Citation

```bibtex
@article{wei2024swerl,
  title={SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution},
  author={Wei, Yuxiang and Duchenne, Olivier and Copet, Jade and Carbonneaux, Quentin and Zhang, Lingming and Fried, Daniel and Synnaeve, Gabriel and Singh, Rishabh and Wang, Sida I.},
  journal={arXiv preprint arXiv:2512.18552},
  year={2024}
}
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.
