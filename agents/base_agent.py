"""
Classe de base pour tous les agents du pipeline.
Chaque agent spécialisé hérite de BaseAgent et implémente run().
"""

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from config import config
from memory import shared_memory
from event_bus import event_bus, Event, EventType


@dataclass
class AgentTask:
    """Tâche confiée à un agent par l'orchestrateur."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    run_id: str = ""
    instruction: str = ""
    context: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # agent_ids requis avant


@dataclass
class AgentResult:
    """Résultat retourné par un agent."""
    agent_id: str
    task_id: str
    run_id: str
    success: bool
    output: Any
    metadata: dict = field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Agent de base.
    
    Fournit :
    - Client Anthropic configuré
    - Gestion des outils (tool_use)
    - Retry automatique avec backoff
    - Pub/sub sur le bus d'événements
    - Accès à la mémoire partagée
    """

    def __init__(self, agent_id: str, system_prompt: str):
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.client = anthropic.AsyncAnthropic(
            api_key=config.anthropic_api_key
        )
        self.tools: list[dict] = []   # définition des outils Anthropic
        self._retry_count = 0

    # ------------------------------------------------------------------
    # Interface publique
    # ------------------------------------------------------------------

    async def execute(self, task: AgentTask) -> AgentResult:
        """Point d'entrée appelé par l'orchestrateur."""
        start = time.time()

        await event_bus.publish(Event(
            type=EventType.AGENT_STARTED,
            run_id=task.run_id,
            source=self.agent_id,
            payload={"task_id": task.task_id, "instruction": task.instruction[:80]}
        ))

        for attempt in range(config.agent.max_retries):
            try:
                output = await self.run(task)
                duration = int((time.time() - start) * 1000)

                result = AgentResult(
                    agent_id=self.agent_id,
                    task_id=task.task_id,
                    run_id=task.run_id,
                    success=True,
                    output=output,
                    duration_ms=duration
                )

                await shared_memory.store_result(task.run_id, self.agent_id, output)
                await event_bus.publish(Event(
                    type=EventType.AGENT_COMPLETED,
                    run_id=task.run_id,
                    source=self.agent_id,
                    payload={"task_id": task.task_id, "duration_ms": duration}
                ))
                return result

            except Exception as e:
                if attempt < config.agent.max_retries - 1:
                    wait = 2 ** attempt
                    await event_bus.publish(Event(
                        type=EventType.AGENT_RETRY,
                        run_id=task.run_id,
                        source=self.agent_id,
                        payload={"attempt": attempt + 1, "error": str(e), "wait": wait}
                    ))
                    await asyncio.sleep(wait)
                else:
                    duration = int((time.time() - start) * 1000)
                    await event_bus.publish(Event(
                        type=EventType.AGENT_FAILED,
                        run_id=task.run_id,
                        source=self.agent_id,
                        payload={"error": str(e)}
                    ))
                    return AgentResult(
                        agent_id=self.agent_id,
                        task_id=task.task_id,
                        run_id=task.run_id,
                        success=False,
                        output=None,
                        duration_ms=duration,
                        error=str(e)
                    )

    @abstractmethod
    async def run(self, task: AgentTask) -> Any:
        """Logique métier de l'agent. À implémenter dans chaque sous-classe."""
        ...

    # ------------------------------------------------------------------
    # Helpers Anthropic
    # ------------------------------------------------------------------

    async def call_claude(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        max_tokens: int = None
    ) -> str:
        """
        Appel simple à Claude. Gère automatiquement la boucle tool_use.
        Retourne le texte final de la réponse.
        """
        current_messages = list(messages)
        active_tools = tools or self.tools

        while True:
            kwargs = {
                "model": config.agent.model,
                "max_tokens": max_tokens or config.agent.max_tokens,
                "system": self.system_prompt,
                "messages": current_messages,
            }
            if active_tools:
                kwargs["tools"] = active_tools

            response = await self.client.messages.create(**kwargs)

            # Collecte tous les blocs texte
            text_blocks = [
                b.text for b in response.content if b.type == "text"
            ]
            tool_blocks = [
                b for b in response.content if b.type == "tool_use"
            ]

            # Pas d'appel d'outil → retourne le texte
            if not tool_blocks or response.stop_reason == "end_turn":
                return "\n".join(text_blocks).strip()

            # Exécute les outils et continue la boucle
            current_messages.append({
                "role": "assistant",
                "content": response.content
            })

            tool_results = []
            for tb in tool_blocks:
                result = await self._execute_tool(tb.name, tb.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tb.id,
                    "content": str(result)
                })

            current_messages.append({
                "role": "user",
                "content": tool_results
            })

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """
        Dispatche l'exécution d'un outil.
        Surcharge dans les agents qui ont des outils spécifiques.
        """
        raise NotImplementedError(
            f"L'agent {self.agent_id} n'a pas implémenté l'outil '{tool_name}'"
        )

    # ------------------------------------------------------------------
    # Accès mémoire
    # ------------------------------------------------------------------

    async def get_previous_results(self, task: AgentTask) -> dict:
        """Récupère les résultats des agents dont on dépend."""
        results = {}
        for dep_agent_id in task.dependencies:
            r = await shared_memory.get_result(task.run_id, dep_agent_id)
            if r:
                results[dep_agent_id] = r
        return results

    async def save_context(self, task: AgentTask, key: str, value: Any) -> None:
        await shared_memory.set_context(task.run_id, f"{self.agent_id}:{key}", value)

    async def get_context(self, task: AgentTask, key: str) -> Optional[Any]:
        return await shared_memory.get_context(task.run_id, f"{self.agent_id}:{key}")

    def __repr__(self):
        return f"<Agent {self.agent_id}>"
