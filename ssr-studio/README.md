# SSR Studio - Self-Play SWE-RL Demo & Research Platform

A complete implementation demonstrating SSR-style self-play for software engineering, where an agent can create its own executable training tasks (bugs + oracle tests) and learn to solve them. Based on the paper ["Toward Training Superintelligent Software Agents through Self-Play SWE-RL"](https://arxiv.org/abs/2512.18552v1).

## 🎯 Overview

SSR Studio implements a complete pipeline for:
1. **Bug Injection** - An injector agent analyzes a codebase and creates realistic, validated bugs
2. **Validation** - 7-step validation ensures bugs are realistic and solvable
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

## ✨ Features

- **Multi-Provider LLM Support**: OpenAI, Anthropic Claude, and local models (vLLM)
- **Secure Docker Sandboxing**: Isolated execution with resource limits
- **7-Step Validation**: Complete SSR paper validation pipeline including inverse mutation testing
- **Real-time Dashboard**: Next.js frontend with live episode tracking
- **CLI Interface**: Full command-line control for automation
- **Metrics & Analytics**: Comprehensive performance tracking

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for development)
- Node.js 20+ (for frontend development)
- OpenAI or Anthropic API key (or local GPU for vLLM)

### Using Docker Compose (Recommended)

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

### Local Development

1. **Install backend dependencies**:
```bash
pip install uv
uv pip install -e ".[dev]"
```

2. **Start PostgreSQL and Redis**:
```bash
docker-compose up -d postgres redis
```

3. **Run the backend**:
```bash
python -m ssr_studio.cli serve
```

4. **Install and run frontend**:
```bash
cd ui
npm install
npm run dev
```

## 📖 Usage

### CLI Commands

```bash
# Start the API server
ssr-studio serve --host 0.0.0.0 --port 8000

# List environments
ssr-studio env list

# Add a new environment
ssr-studio env add my-python-project python:3.11-slim --language python

# Run an episode
ssr-studio run <env-id> --max-attempts 3 --injector-model gpt-4-turbo

# View episode history
ssr-studio episodes --status completed --limit 10

# Show episode details
ssr-studio show <episode-id>

# View metrics summary
ssr-studio metrics
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

## 🔬 Validation Pipeline

SSR Studio implements all 7 validation steps from the SSR paper:

| Step | Name | Description |
|------|------|-------------|
| 1 | Test Files Existence | Verify oracle test file was created |
| 2 | Parser Validity | Ensure modified files have valid syntax |
| 3 | Original Tests Pass | Existing tests still pass on clean codebase |
| 4 | Bug Scope | Bug is contained to allowed files/lines |
| 5 | Bug Validity | Oracle test fails on buggy code |
| 6 | Test Weakening Validity | Oracle test passes on clean code |
| 7 | Inverse Mutation Testing | Random mutations don't accidentally pass oracle test |

## 🏗️ Architecture

```
ssr-studio/
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

## 🐳 Running Local Models

To use local models with vLLM:

```bash
# Start with vLLM profile
docker-compose --profile local-models up -d

# Configure to use local models
export SSR_DEFAULT_MODEL_PROVIDER=local
```

Requires NVIDIA GPU with sufficient VRAM for the chosen model.

## 📊 Metrics

The dashboard tracks:
- Episode success rate
- Average reward over time
- Validation step pass rates
- Solver attempt statistics
- Model performance comparison

Export metrics in Prometheus format at `/metrics` endpoint.

## 🔒 Security

- All code execution happens in isolated Docker containers
- Network access disabled by default in sandboxes
- Resource limits (CPU, memory) enforced
- Non-root container execution
- No new privileges flag set

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## 📚 References

- [Toward Training Superintelligent Software Agents through Self-Play SWE-RL](https://arxiv.org/abs/2512.18552v1)
- [SWE-bench: Can Language Models Resolve Real-World GitHub Issues?](https://arxiv.org/abs/2310.06770)

## 📄 License

MIT License - see LICENSE file for details.
