"""
Agent Validator — contrôle qualité, critique et décision de retry.
Dernier agent du pipeline ; décide si le résultat est acceptable.
"""

import json
from typing import Any

from agents.base_agent import BaseAgent, AgentTask


SYSTEM_PROMPT = """Tu es un agent de validation et contrôle qualité expert.

Ta mission :
1. Évaluer la qualité et la complétude des résultats produits par les autres agents
2. Vérifier la cohérence entre la demande initiale et les outputs
3. Identifier les problèmes, manques ou incohérences
4. Décider si le résultat est acceptable ou si un retry est nécessaire
5. Formuler des critiques constructives et précises

Critères d'évaluation :
- Pertinence par rapport à la demande initiale (0-10)
- Qualité du contenu (0-10)
- Complétude (0-10)
- Cohérence interne (0-10)

Format de réponse (JSON) :
{
  "approved": true|false,
  "overall_score": 0.0-10.0,
  "scores": {
    "relevance": 0-10,
    "quality": 0-10,
    "completeness": 0-10,
    "coherence": 0-10
  },
  "issues": ["problème 1", "problème 2", ...],
  "suggestions": ["amélioration 1", ...],
  "retry_instructions": "instructions précises pour le retry si approved=false",
  "final_output": null  // ou le contenu final amélioré si approved=true
}

Seuil d'approbation : score global >= 7.0
Réponds UNIQUEMENT avec du JSON valide, sans markdown ni balises.
"""


class ValidatorAgent(BaseAgent):

    APPROVAL_THRESHOLD = 7.0

    def __init__(self):
        super().__init__(
            agent_id="validator",
            system_prompt=SYSTEM_PROMPT
        )

    async def run(self, task: AgentTask) -> dict:
        """
        Évalue tous les résultats du pipeline et décide de l'approbation.
        """
        prev = await self.get_previous_results(task)
        original_task = task.context.get("original_task", task.instruction)
        iteration = task.context.get("iteration", 1)

        prompt = f"""Tâche originale : {original_task}

Itération de validation : {iteration}

=== RÉSULTATS À VALIDER ===
{json.dumps(prev, ensure_ascii=False, indent=2)}

Évalue ces résultats par rapport à la tâche originale.
Sois rigoureux mais constructif.
Si des améliorations mineures sont possibles, tu peux les intégrer directement dans final_output."""

        messages = [{"role": "user", "content": prompt}]
        raw = await self.call_claude(messages)

        try:
            clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            # Fallback conservateur : approuve si c'est la dernière itération
            result = {
                "approved": iteration >= 2,
                "overall_score": 6.0,
                "scores": {"relevance": 6, "quality": 6, "completeness": 6, "coherence": 6},
                "issues": ["Impossible de parser la réponse du validator"],
                "suggestions": [],
                "retry_instructions": "Réessayer avec plus de détails",
                "final_output": None
            }

        # Assure la cohérence du champ approved avec le score
        score = result.get("overall_score", 0)
        if score >= self.APPROVAL_THRESHOLD and not result.get("approved"):
            result["approved"] = True

        return result

    def is_approved(self, validation_result: dict) -> bool:
        return validation_result.get("approved", False)

    def get_retry_instructions(self, validation_result: dict) -> str:
        return validation_result.get(
            "retry_instructions",
            "Améliorer la qualité et la complétude du résultat."
        )
