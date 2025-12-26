# Changelog

All notable changes to SSR Studio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-12-26

### Added

- Initial release of SSR Studio
- **Core Pipeline**
  - Bug injection agent with multiple mutation strategies
  - 7-step SSR validation engine
  - Bug solver agent with iterative fixing
  - Episode orchestrator for pipeline coordination
  
- **LLM Support**
  - OpenAI provider (GPT-4, GPT-4o, GPT-3.5)
  - Anthropic provider (Claude 3 Opus, Sonnet, Haiku)
  - Local model support via vLLM
  
- **Infrastructure**
  - Docker-based sandbox execution with security controls
  - PostgreSQL database with async SQLAlchemy
  - Local and S3 artifact storage backends
  - Redis support for caching (optional)
  
- **Interfaces**
  - FastAPI REST API with OpenAPI docs
  - CLI tool for automation
  - Next.js dashboard with real-time updates
  
- **Demo**
  - Self-contained `demo.py` script
  - Calculator example project with 45 tests
  - Full inject → validate → solve pipeline demonstration

### Security

- Network-isolated container execution
- Resource limits (CPU, memory)
- Non-root container users
- Input validation on all API endpoints

---

## Future Roadmap

### [0.2.0] - Planned

- [ ] Batch episode execution
- [ ] Model performance comparison dashboard
- [ ] Export training data in various formats
- [ ] Support for more programming languages

### [0.3.0] - Planned

- [ ] Fine-tuning pipeline integration
- [ ] SWE-bench evaluation mode
- [ ] Multi-repository support
- [ ] Collaborative annotation interface
