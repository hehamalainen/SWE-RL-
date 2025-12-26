# Contributing to SSR Studio

Thank you for your interest in contributing to SSR Studio! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment:

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Install frontend dependencies
cd ui && npm install
```

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for sandbox execution)
- OpenAI or Anthropic API key (for testing with LLMs)

### Running Locally

```bash
# Start backend services
docker-compose up -d postgres redis

# Run the API server
python -m ssr_studio.cli serve

# In another terminal, run the frontend
cd ui && npm run dev
```

### Running Tests

```bash
# Python tests
pytest tests/ -v

# Example project tests
cd examples/calculator && pytest test_calculator.py -v
```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Format with `black` and `isort`
- Lint with `ruff`

```bash
black src/
isort src/
ruff check src/
```

### TypeScript/React

- Use TypeScript strictly
- Format with Prettier
- Follow React best practices

```bash
cd ui && npm run lint && npm run format
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation if needed
6. Submit a pull request

### PR Guidelines

- Keep changes focused and atomic
- Write clear commit messages
- Include tests for new features
- Update README if adding new features
- Reference any related issues

## Reporting Issues

When reporting issues, please include:

- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

## Feature Requests

Feature requests are welcome! Please:

- Check existing issues first
- Describe the use case
- Explain why it would be valuable
- Consider if you'd like to implement it

## Architecture Overview

```
src/ssr_studio/
├── api.py           # FastAPI endpoints
├── orchestrator.py  # Episode pipeline coordination
├── sandbox.py       # Docker sandbox execution
├── validator.py     # 7-step SSR validation
├── model_gateway.py # LLM provider abstraction
└── agents/
    ├── injector.py  # Bug injection agent
    └── solver.py    # Bug solving agent
```

## Key Concepts

### SSR Episode Pipeline

1. **Inject** - LLM creates a bug and oracle test
2. **Validate** - Verify bug is realistic and testable
3. **Solve** - LLM attempts to fix using only oracle test
4. **Evaluate** - Calculate reward based on success

### Validation Steps

1. Test files existence
2. Parser validity
3. Original tests pass
4. Bug scope check
5. Bug validity (oracle fails on bug)
6. Test weakening validity (oracle passes on clean)
7. Inverse mutation testing

## Questions?

Feel free to open an issue for questions or join discussions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
