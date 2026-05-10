"""
Configuration centralisée du pipeline multi-agents.
Toutes les constantes, modèles et paramètres sont ici.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3
    max_retries: int = 3
    timeout_seconds: int = 60


@dataclass
class MemoryConfig:
    backend: str = "dict"          # "dict" | "redis"
    redis_url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 3600        # 1h par défaut
    max_history: int = 50          # messages max par agent


@dataclass
class PipelineConfig:
    max_parallel_agents: int = 4
    max_iterations: int = 10       # boucles orchestrateur max
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
            raise ValueError(
                "ANTHROPIC_API_KEY manquant. "
                "Exportez-le: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        return self


# Instance globale
config = Config().validate() if os.environ.get("ANTHROPIC_API_KEY") else Config()
