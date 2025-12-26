"""
Configuration management for SSR Studio.

Handles loading configuration from environment variables, YAML files,
and provides sensible defaults for all settings.
"""

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class InjectionStrategy(str, Enum):
    """Bug injection strategy modes as described in the SSR paper."""
    DIRECT = "direct"  # Baseline; tends to produce trivial bugs
    REMOVAL_ONLY = "removal_only"  # Remove hunks/files but keep repo runnable
    HISTORY_AWARE = "history_aware"  # Mixture of removal and history-aware reversion


class Settings(BaseSettings):
    """Main application settings."""
    
    model_config = SettingsConfigDict(
        env_prefix="SSR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Application settings
    app_name: str = "SSR Studio"
    debug: bool = False
    log_level: str = "INFO"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    
    # Database settings
    database_url: str = "postgresql+asyncpg://ssr:ssr@localhost:5432/ssr_studio"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Redis settings (for task queue)
    redis_url: str = "redis://localhost:6379/0"
    
    # Storage settings
    storage_backend: Literal["local", "s3"] = "local"
    storage_path: Path = Path("/data/ssr-studio/artifacts")
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    
    # Docker/Sandbox settings
    docker_host: str | None = None
    sandbox_network_enabled: bool = False  # No network by default for security
    sandbox_cpu_limit: float = 2.0  # CPU cores
    sandbox_memory_limit: str = "4g"
    sandbox_timeout_seconds: int = 3600  # 1 hour max per episode
    sandbox_bash_timeout: int = 300  # 5 min per bash command
    
    # Model provider settings
    model_provider: Literal["openai", "anthropic", "local"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    local_model_url: str = "http://localhost:8080/v1"
    local_model_name: str = "codellama"
    
    # Injection parameters (SSR paper §2.3)
    injection_strategy: InjectionStrategy = InjectionStrategy.REMOVAL_ONLY
    min_passing_tests: int = 10
    min_changed_files: int = 1
    min_failing_tests: int = 1
    max_test_runtime_sec: int = 90
    
    # Solver parameters (SSR paper §2.4)
    solver_attempts_per_bug: int = 4  # Default 4 for MVP; 8 for research parity
    solver_max_tool_steps: int = 50
    solver_max_tokens: int = 100000
    solver_temperature: float = 0.7
    solver_top_p: float = 0.95
    
    # Reward parameters (SSR paper §2.3)
    reward_alpha: float = 0.8  # Penalty for trivially easy/impossible bugs
    
    # Training settings (P2 feature)
    training_enabled: bool = False
    training_lora_r: int = 16
    training_lora_alpha: int = 32
    training_learning_rate: float = 1e-4
    training_batch_size: int = 4
    training_gradient_accumulation_steps: int = 4
    training_kl_coef: float = 0.1


class ValidatorConfig(BaseSettings):
    """Validator-specific configuration."""
    
    model_config = SettingsConfigDict(env_prefix="SSR_VALIDATOR_")
    
    # Validation retry settings
    test_retry_count: int = 2  # Retry flaky tests
    test_retry_delay_ms: int = 1000
    
    # Inverse mutation testing
    enable_inverse_mutation: bool = True
    
    # Log truncation
    max_log_size_bytes: int = 1_000_000  # 1MB


class UIConfig(BaseSettings):
    """UI-specific configuration."""
    
    model_config = SettingsConfigDict(env_prefix="SSR_UI_")
    
    # Pagination
    default_page_size: int = 20
    max_page_size: int = 100
    
    # Demo mode
    demo_mode: bool = True
    demo_environments: list[str] = Field(default_factory=list)


# Global settings instance
settings = Settings()
validator_config = ValidatorConfig()
ui_config = UIConfig()


def load_yaml_config(path: Path) -> dict:
    """Load configuration from a YAML file."""
    import yaml
    
    if not path.exists():
        return {}
    
    with open(path) as f:
        return yaml.safe_load(f) or {}
