# SSR Studio - Self-Play SWE-RL Demo & Research Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![arXiv](https://img.shields.io/badge/arXiv-2512.18552-b31b1b.svg)](https://arxiv.org/abs/2512.18552)

A complete implementation demonstrating **SSR-style self-play** for software engineering, where an agent can create its own executable training tasks (bugs + oracle tests) and learn to solve them.

---

## 🙏 Acknowledgments

This project is an implementation inspired by the groundbreaking research paper:

> **"SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution"**
>
> **Authors:** Yuxiang Wei, Olivier Duchenne, Jade Copet, Quentin Carbonneaux, Lingming Zhang, Daniel Fried, Gabriel Synnaeve, Rishabh Singh, Sida I. Wang
>
> **Affiliations:** Meta AI (FAIR), University of Illinois Urbana-Champaign, Carnegie Mellon University
>
> 📄 **Paper:** [arXiv:2512.18552](https://arxiv.org/abs/2512.18552) (December 2024)

We extend our sincere gratitude to the research team for their innovative work on:
- Demonstrating that **reinforcement learning on real-world software evolution data** can significantly advance LLM reasoning
- Introducing the **SSR (Self-play SWE-RL)** paradigm for autonomous task generation
- Achieving state-of-the-art results on SWE-bench with openly available methods
- Providing detailed methodology for **bug injection validation** (the 7-step process we implement here)

This implementation aims to make the SSR concepts accessible and explorable for the broader community.

---

## 🎯 Overview

SSR Studio implements the complete **self-play pipeline** from the paper:

1. **Bug Injection** - An LLM agent analyzes a codebase and creates realistic, validated bugs
2. **Validation** - 7-step validation ensures bugs are realistic and solvable (per SSR paper)
3. **Bug Solving** - A solver agent attempts to fix the bug using only the oracle test
4. **Evaluation** - Rewards are calculated based on solve success

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SSR Episode Pipeline                             │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────────┐     │
│  │ Injector │───▶│ Validator │───▶│  Solver  │───▶│   Evaluate   │     │
│  │  Agent   │    │ (7 steps) │    │  Agent   │    │    Reward    │     │
│  └──────────┘    └───────────┘    └──────────┘    └──────────────┘     │
│       │               │                │                  │              │
│       ▼               ▼                ▼                  ▼              │
│   Bug Diff +      Validated       Patch +             +1.0 or 0.0       │
│  Oracle Test       Artifact     Test Results                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### The Core Insight

From the SSR paper:
> *"An agent can create its own executable training tasks and learn to solve them."*

This enables:
- **Unlimited training data** - No reliance on human-curated bug datasets
- **Self-improvement loop** - Agent learns from self-generated challenges
- **Quality control** - Rigorous validation ensures generated tasks are meaningful

---

## ✨ Features

- **Multi-Provider LLM Support**: OpenAI GPT-4, Anthropic Claude, and local models (vLLM)
- **Secure Docker Sandboxing**: Isolated execution with network disabled, resource limits
- **7-Step Validation**: Complete SSR paper validation pipeline including inverse mutation testing
- **Real-time Dashboard**: Next.js frontend with live episode tracking
- **CLI Interface**: Full command-line control for automation
- **Metrics & Analytics**: Comprehensive performance tracking
- **Self-contained Demo**: Run the full pipeline with one command

---

## 🚀 Quick Start

### Try the Demo (Fastest)

```bash
cd ssr-studio
pip install openai anthropic rich pytest
python demo.py --api-key YOUR_OPENAI_KEY
```

This runs a complete episode:
1. Injects a bug into the example calculator project
2. Validates the bug meets all 7 SSR criteria
3. Attempts to solve using a separate LLM call
4. Reports success/failure with full diffs

### Prerequisites

- Python 3.11+
- Docker (for sandbox execution in full platform)
- OpenAI or Anthropic API key

### Full Platform Setup

1. **Clone and setup**:
```bash
cd ssr-studio
cp .env.example .env
# Edit .env with your API keys
```

2. **Start all services**:
```bash
docker-compose up -d
```

3. **Access the dashboard**:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 🔬 The 7 Validation Steps

Following the SSR paper exactly, we validate each injected bug:

| Step | Name | Purpose |
|------|------|---------|
| 1 | **Test Files Existence** | Oracle test file was created |
| 2 | **Parser Validity** | Modified files have valid syntax |
| 3 | **Original Tests Pass** | Existing tests still pass on clean code |
| 4 | **Bug Scope** | Bug is contained to allowed files/lines |
| 5 | **Bug Validity** | Oracle test fails on buggy code |
| 6 | **Test Weakening Validity** | Oracle test passes on clean code |
| 7 | **Inverse Mutation Testing** | Random mutations don't accidentally pass oracle |

Step 7 is particularly clever: it ensures the oracle test is specific to *this* bug, not just any change.

---

## 📖 Usage

### Demo Script

```bash
# With OpenAI
python demo.py --api-key sk-...

# With Anthropic
python demo.py --provider anthropic --api-key sk-ant-...

# With specific model
python demo.py --model gpt-4o --api-key sk-...

# Multiple solve attempts
python demo.py --max-attempts 5 --api-key sk-...
```

### CLI Commands

```bash
# Start the API server
python -m ssr_studio.cli serve --host 0.0.0.0 --port 8000

# List environments
python -m ssr_studio.cli env list

# Add a new environment
python -m ssr_studio.cli env add my-project python:3.11-slim --language python

# Run an episode
python -m ssr_studio.cli run <env-id> --max-attempts 3

# View episode history
python -m ssr_studio.cli episodes --status completed --limit 10

# Show episode details
python -m ssr_studio.cli show <episode-id>

# View metrics summary
python -m ssr_studio.cli metrics
```

### API Examples

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

# Create an environment
env = client.post("/api/environments", json={
    "name": "requests-2.31.0",
    "docker_image_ref": "python:3.11-slim",
    "language_hint": "python"
}).json()

# Start an episode
episode = client.post("/api/episodes", json={
    "env_id": env["env_id"],
    "max_solver_attempts": 3,
    "injector_model_id": "gpt-4-turbo",
    "solver_model_id": "gpt-4-turbo"
}).json()

# Check status
status = client.get(f"/api/episodes/{episode['episode_id']}").json()
print(f"Status: {status['status']}, Reward: {status.get('final_reward')}")
```

---

## 🏗️ Architecture

```
ssr-studio/
├── demo.py                 # Self-contained demo script
├── examples/
│   └── calculator/         # Example project (45 tests)
├── src/ssr_studio/
│   ├── api.py              # FastAPI routes
│   ├── config.py           # Configuration management
│   ├── database.py         # SQLAlchemy models
│   ├── models.py           # Pydantic data models
│   ├── orchestrator.py     # Episode pipeline coordinator
│   ├── sandbox.py          # Docker sandbox execution
│   ├── storage.py          # Artifact storage (local/S3)
│   ├── validator.py        # 7-step validation engine
│   ├── model_gateway.py    # Multi-provider LLM client
│   ├── tools.py            # Agent tool definitions
│   ├── cli.py              # CLI interface
│   └── agents/
│       ├── injector.py     # Bug injection agent
│       └── solver.py       # Bug solving agent
├── ui/                     # Next.js frontend
│   └── src/
│       ├── app/            # App router pages
│       ├── components/     # React components
│       └── lib/            # Utilities and API client
├── configs/                # YAML configuration files
├── docker-compose.yml      # Container orchestration
└── Dockerfile              # Backend container
```

---

## ⚙️ Configuration

Configuration can be set via:
1. YAML files in `configs/`
2. Environment variables (prefixed with `SSR_`)
3. CLI arguments

See `configs/default.yaml` for all available options.

### Key Settings

| Setting | Env Var | Description |
|---------|---------|-------------|
| OpenAI API Key | `SSR_OPENAI_API_KEY` | Required for GPT models |
| Anthropic API Key | `SSR_ANTHROPIC_API_KEY` | Required for Claude models |
| Database URL | `SSR_DATABASE_URL` | PostgreSQL connection string |
| Sandbox Timeout | `SSR_SANDBOX_TIMEOUT_SECONDS` | Max execution time (default: 300s) |
| Storage Backend | `SSR_STORAGE_BACKEND` | `local` or `s3` |

---

## 🐳 Running Local Models

To use local models with vLLM:

```bash
# Start with vLLM profile (requires NVIDIA GPU)
docker-compose --profile local-models up -d

# Configure to use local models
export SSR_DEFAULT_MODEL_PROVIDER=local
```

---

## 🔒 Security

- All code execution happens in isolated Docker containers
- Network access disabled by default in sandboxes
- Resource limits (CPU, memory) enforced
- Non-root container execution
- No new privileges flag set

---

## 📊 Research Applications

This implementation can be used for:

1. **Exploring SSR dynamics** - How do injection and solving capabilities co-evolve?
2. **Model comparison** - Which LLMs are better at injection vs. solving?
3. **Training data generation** - Create validated bug/fix pairs for fine-tuning
4. **Benchmark creation** - Generate new SWE-bench-style tasks

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

---

## 📚 References

### Primary Reference

- **SWE-RL Paper**: Wei, Y., et al. (2024). "SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution." [arXiv:2512.18552](https://arxiv.org/abs/2512.18552)

### Related Work

- [SWE-bench](https://www.swebench.com/) - The benchmark for evaluating LLMs on real GitHub issues
- [SWE-agent](https://github.com/princeton-nlp/SWE-agent) - Agent framework for software engineering tasks
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) - Platform for AI software developers

---

## 📄 License

MIT License - see [LICENSE](../LICENSE) file for details.

---

## ⭐ Citation

If you use this implementation in your research, please cite the original SSR paper:

```bibtex
@article{wei2024swerl,
  title={SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution},
  author={Wei, Yuxiang and Duchenne, Olivier and Copet, Jade and Carbonneaux, Quentin and Zhang, Lingming and Fried, Daniel and Synnaeve, Gabriel and Singh, Rishabh and Wang, Sida I.},
  journal={arXiv preprint arXiv:2512.18552},
  year={2024}
}
```
