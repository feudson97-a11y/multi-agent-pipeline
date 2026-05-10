"""
Agent Researcher — recherche web et synthèse d'information.
Utilise le web_search tool natif d'Anthropic.
"""

import json
from typing import Any

from agents.base_agent import BaseAgent, AgentTask


SYSTEM_PROMPT = """Tu es un agent de recherche expert.

Ta mission :
1. Analyser la demande de recherche fournie
2. Effectuer des recherches web ciblées et pertinentes
3. Synthétiser les informations trouvées de manière structurée
4. Citer tes sources
5. Identifier les lacunes ou incertitudes dans les résultats

Format de réponse attendu (JSON) :
{
  "summary": "résumé en 2-3 phrases",
  "key_findings": ["point 1", "point 2", ...],
  "sources": ["url1", "url2", ...],
  "gaps": ["information manquante 1", ...],
  "raw_content": "contenu brut détaillé"
}

Réponds UNIQUEMENT avec du JSON valide, sans markdown ni balises.
"""


class ResearcherAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            agent_id="researcher",
            system_prompt=SYSTEM_PROMPT
        )
        # Outil web_search natif Anthropic
        self.tools = [
            {
                "type": "web_search_20250305",
                "name": "web_search"
            }
        ]

    async def run(self, task: AgentTask) -> dict:
        """
        Effectue des recherches web sur le sujet donné.
        Retourne un dict structuré avec les résultats.
        """
        # Contexte additionnel depuis les dépendances (si présentes)
        prev = await self.get_previous_results(task)
        context_str = ""
        if prev:
            context_str = f"\n\nContexte des agents précédents:\n{json.dumps(prev, ensure_ascii=False, indent=2)}"

        messages = [
            {
                "role": "user",
                "content": (
                    f"Sujet de recherche: {task.instruction}"
                    f"{context_str}"
                    f"\n\nContexte additionnel: {json.dumps(task.context, ensure_ascii=False)}"
                )
            }
        ]

        raw = await self.call_claude(messages, tools=self.tools)

        # Parse JSON robuste
        try:
            # Nettoie les éventuels ```json ... ```
            clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            # Fallback: renvoie le texte brut structuré
            result = {
                "summary": raw[:500],
                "key_findings": [],
                "sources": [],
                "gaps": [],
                "raw_content": raw
            }

        await self.save_context(task, "research_done", True)
        return result
