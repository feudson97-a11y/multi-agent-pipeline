"""
Orchestrateur du pipeline multi-agents.

Responsabilités :
- Décomposer la tâche utilisateur en sous-tâches
- Dispatcher les tâches aux agents dans le bon ordre
- Gérer les dépendances entre agents
- Piloter la boucle de validation / retry
- Agréger et retourner le résultat final
"""

import asyncio
import json
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from config import config
from memory import shared_memory
from event_bus import event_bus, Event, EventType
from agents import (
    AgentTask, AgentResult,
    ResearcherAgent, AnalystAgent, WriterAgent, ValidatorAgent
)


ORCHESTRATOR_SYSTEM = """Tu es un orchestrateur de pipeline multi-agents.

Étant donné une tâche utilisateur, génère un plan d'exécution en JSON.

Agents disponibles :
- researcher : recherche web, collecte d'informations
- analyst    : analyse de données, raisonnement, calculs
- writer     : génération de contenu, rédaction, formatage
- validator  : validation qualité (toujours en dernier)

Format du plan (JSON strict) :
{
  "steps": [
    {
      "agent": "researcher|analyst|writer|validator",
      "instruction": "instruction précise pour cet agent",
      "dependencies": [],   // liste des agent_ids dont les résultats sont requis avant
      "context": {}         // paramètres additionnels (format, tone, etc.)
    }
  ],
  "rationale": "explication du plan en 1-2 phrases"
}

Règles :
- Le validator est TOUJOURS la dernière étape
- Chaque agent ne peut apparaître qu'une fois par plan
- Les dépendances doivent être des agents qui apparaissent avant dans les steps
- Génère le JSON minimal nécessaire pour accomplir la tâche
Réponds UNIQUEMENT avec du JSON valide.
"""


@dataclass
class PipelineRun:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task: str = ""
    plan: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    iteration: int = 0
    status: str = "pending"
    started_at: float = field(default_factory=time.time)
    final_output: Any = None


class Orchestrator:
    """Orchestrateur principal du pipeline."""

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self._agents = {
            "researcher": ResearcherAgent(),
            "analyst": AnalystAgent(),
            "writer": WriterAgent(),
            "validator": ValidatorAgent(),
        }
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Abonnements aux événements pour logging/observabilité."""

        @event_bus.on_any
        async def log_event(event: Event):
            icon = {
                EventType.AGENT_STARTED: "▶",
                EventType.AGENT_COMPLETED: "✓",
                EventType.AGENT_FAILED: "✗",
                EventType.AGENT_RETRY: "↺",
                EventType.PIPELINE_STARTED: "🚀",
                EventType.PIPELINE_COMPLETED: "🎉",
                EventType.PIPELINE_FAILED: "💥",
            }.get(event.type, "·")
            print(f"  {icon} [{event.source}] {event.type.value}", end="")
            if event.payload.get("duration_ms"):
                print(f" ({event.payload['duration_ms']}ms)", end="")
            if event.payload.get("error"):
                print(f" — {event.payload['error'][:60]}", end="")
            print()

    # ------------------------------------------------------------------
    # Point d'entrée principal
    # ------------------------------------------------------------------

    async def run(self, task: str, output_format: str = "markdown") -> PipelineRun:
        """
        Exécute le pipeline complet pour une tâche donnée.
        
        Args:
            task: La tâche en langage naturel
            output_format: Format de sortie (markdown, json, plain_text, report)
        
        Returns:
            PipelineRun avec tous les résultats
        """
        run = PipelineRun(task=task)
        print(f"\n{'='*60}")
        print(f"Pipeline démarré | run_id={run.run_id}")
        print(f"Tâche: {task[:80]}")
        print(f"{'='*60}")

        await event_bus.start()
        await event_bus.publish(Event(
            type=EventType.PIPELINE_STARTED,
            run_id=run.run_id,
            source="orchestrator",
            payload={"task": task}
        ))

        await shared_memory.set_task(run.run_id, task)
        await shared_memory.set_status(run.run_id, "planning")

        try:
            # 1. Génération du plan
            print(f"\n📋 Planification...")
            run.plan = await self._plan(task, output_format)
            await shared_memory.set_plan(run.run_id, run.plan)
            print(f"   Rationale: {run.plan.get('rationale', '')[:80]}")

            # 2. Boucle d'exécution + validation
            approved = False
            retry_instructions = ""

            for iteration in range(1, config.pipeline.max_iterations + 1):
                run.iteration = iteration
                print(f"\n🔄 Itération {iteration}/{config.pipeline.max_iterations}")

                await shared_memory.set_status(run.run_id, f"executing_iter_{iteration}")

                # Si retry, on régénère le plan avec les instructions
                if iteration > 1 and retry_instructions:
                    print(f"   ↺ Retry avec: {retry_instructions[:80]}")
                    run.plan = await self._plan(task, output_format, retry_instructions)

                # 3. Exécution des étapes
                results = await self._execute_plan(run)
                run.results = results

                # 4. Vérification validation
                validator_result = results.get("validator", {})
                if validator_result.get("approved"):
                    approved = True
                    run.final_output = (
                        validator_result.get("final_output")
                        or results.get("writer", {}).get("content")
                        or json.dumps(results, ensure_ascii=False, indent=2)
                    )
                    break
                else:
                    retry_instructions = validator_result.get(
                        "retry_instructions", "Améliorer la qualité."
                    )
                    # Nettoie les résultats partiels pour le retry
                    await shared_memory.clear_run(run.run_id)

            if not approved:
                # Retourne le meilleur résultat disponible même sans approbation
                run.final_output = (
                    run.results.get("writer", {}).get("content")
                    or json.dumps(run.results, ensure_ascii=False, indent=2)
                )

            run.status = "completed" if approved else "completed_with_warnings"
            await shared_memory.set_status(run.run_id, run.status)

            await event_bus.publish(Event(
                type=EventType.PIPELINE_COMPLETED,
                run_id=run.run_id,
                source="orchestrator",
                payload={
                    "approved": approved,
                    "iterations": run.iteration,
                    "duration_s": round(time.time() - run.started_at, 2)
                }
            ))

            print(f"\n{'='*60}")
            print(f"✅ Pipeline terminé | {run.iteration} itération(s) | "
                  f"{round(time.time() - run.started_at, 1)}s")
            print(f"{'='*60}\n")

        except Exception as e:
            run.status = "failed"
            await event_bus.publish(Event(
                type=EventType.PIPELINE_FAILED,
                run_id=run.run_id,
                source="orchestrator",
                payload={"error": str(e)}
            ))
            raise

        finally:
            await event_bus.stop()

        return run

    # ------------------------------------------------------------------
    # Planification
    # ------------------------------------------------------------------

    async def _plan(
        self,
        task: str,
        output_format: str,
        retry_context: str = ""
    ) -> dict:
        """Génère le plan d'exécution via Claude."""
        prompt = f"Tâche: {task}\nFormat de sortie souhaité: {output_format}"
        if retry_context:
            prompt += f"\n\nRetry nécessaire. Instructions: {retry_context}"

        response = await self.client.messages.create(
            model=config.agent.model,
            max_tokens=1024,
            system=ORCHESTRATOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        clean = raw.removeprefix("```json").removesuffix("```").strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Plan par défaut si parsing échoue
            return {
                "steps": [
                    {"agent": "researcher", "instruction": task, "dependencies": [], "context": {}},
                    {"agent": "analyst", "instruction": f"Analyser: {task}", "dependencies": ["researcher"], "context": {}},
                    {"agent": "writer", "instruction": task, "dependencies": ["researcher", "analyst"], "context": {"format": output_format}},
                    {"agent": "validator", "instruction": task, "dependencies": ["researcher", "analyst", "writer"], "context": {"original_task": task}},
                ],
                "rationale": "Plan par défaut (fallback)"
            }

    # ------------------------------------------------------------------
    # Exécution
    # ------------------------------------------------------------------

    async def _execute_plan(self, run: PipelineRun) -> dict:
        """
        Exécute les étapes du plan en respectant les dépendances.
        Les étapes sans dépendances en attente s'exécutent en parallèle.
        """
        steps = run.plan.get("steps", [])
        completed: set[str] = set()
        results: dict[str, Any] = {}

        # Regroupement par niveau de dépendance (topological sort simple)
        def can_run(step: dict) -> bool:
            return all(dep in completed for dep in step.get("dependencies", []))

        pending = list(steps)

        while pending:
            # Trouve toutes les étapes prêtes à s'exécuter
            ready = [s for s in pending if can_run(s)]
            if not ready:
                # Dépendances circulaires ou manquantes
                print(f"  ⚠️  Blocage détecté, exécution forcée du premier step")
                ready = [pending[0]]

            # Exécution parallèle des étapes prêtes
            print(f"\n  Exécution parallèle: {[s['agent'] for s in ready]}")
            tasks = [
                self._run_step(step, run)
                for step in ready
            ]
            step_results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(ready, step_results):
                agent_id = step["agent"]
                if isinstance(result, Exception):
                    print(f"  ✗ {agent_id}: {result}")
                    results[agent_id] = {"error": str(result)}
                else:
                    results[agent_id] = result
                completed.add(agent_id)

            pending = [s for s in pending if s["agent"] not in completed]

        return results

    async def _run_step(self, step: dict, run: PipelineRun) -> Any:
        """Exécute une étape du plan via l'agent correspondant."""
        agent_id = step["agent"]
        agent = self._agents.get(agent_id)

        if not agent:
            raise ValueError(f"Agent inconnu: {agent_id}")

        # Enrichit le contexte avec les métadonnées du run
        context = dict(step.get("context", {}))
        context["original_task"] = run.task
        context["iteration"] = run.iteration
        context["run_id"] = run.run_id

        task = AgentTask(
            run_id=run.run_id,
            instruction=step.get("instruction", run.task),
            context=context,
            dependencies=step.get("dependencies", [])
        )

        result = await agent.execute(task)

        if result.success:
            return result.output
        else:
            raise RuntimeError(f"Agent {agent_id} failed: {result.error}")
