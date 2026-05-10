import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 1024
    temperature: float = 0.3
    max_retries: int = 1
    timeout_seconds: int = 60


@dataclass
class MemoryConfig:
    backend: str = "dict"
    redis_url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 3600
    max_history: int = 50


@dataclass
class PipelineConfig:
    max_parallel_agents: int = 4
    max_iterations: int = 1
    enable_validator: bool = True
    enable_observability: bool = True
    log_level: str = "INFO"


@dataclass
class Config:
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    agent: AgentConfig = field(default_factory=AgentConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    def validate(self):
        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY manquant.")
        return self


config = Config().validate() if os.environ.get("ANTHROPIC_API_KEY") else Config()