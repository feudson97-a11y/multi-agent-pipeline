"""
Agent Writer — génération de contenu structuré et formaté.
Transforme les analyses en documents lisibles.
"""

import json
from typing import Any

from agents.base_agent import BaseAgent, AgentTask


SYSTEM_PROMPT = """Tu es un agent rédacteur expert.

Ta mission :
1. Prendre les données brutes et analyses fournies
2. Produire un document final clair, bien structuré et adapté au format demandé
3. Respecter le ton, la longueur et le format spécifiés dans la tâche
4. Assurer la cohérence narrative et la lisibilité

Formats supportés : markdown, json, plain_text, html, report

Format de réponse (JSON) :
{
  "format": "markdown|json|plain_text|html|report",
  "title": "titre du document",
  "content": "contenu complet du document",
  "word_count": 0,
  "sections": ["section1", "section2", ...]
}

Réponds UNIQUEMENT avec du JSON valide, sans markdown ni balises externes.
"""


class WriterAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            agent_id="writer",
            system_prompt=SYSTEM_PROMPT
        )

    async def run(self, task: AgentTask) -> dict:
        """
        Génère le document final à partir des résultats des agents précédents.
        """
        prev = await self.get_previous_results(task)

        # Extrait le format désiré depuis le contexte (défaut: markdown)
        output_format = task.context.get("format", "markdown")
        tone = task.context.get("tone", "professionnel")
        max_words = task.context.get("max_words", 800)

        # Prépare le contexte enrichi
        research = prev.get("researcher", {})
        analysis = prev.get("analyst", {})

        prompt_content = f"""Tâche de rédaction: {task.instruction}

Format souhaité: {output_format}
Ton: {tone}
Longueur maximale: {max_words} mots

=== DONNÉES DE RECHERCHE ===
{json.dumps(research, ensure_ascii=False, indent=2)}

=== ANALYSE ===
{json.dumps(analysis, ensure_ascii=False, indent=2)}

=== CONTEXTE ADDITIONNEL ===
{json.dumps(task.context, ensure_ascii=False, indent=2)}

Génère le document final dans le format demandé."""

        messages = [{"role": "user", "content": prompt_content}]
        raw = await self.call_claude(messages)

        try:
            clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            # Fallback: le texte brut devient le contenu
            result = {
                "format": output_format,
                "title": task.instruction[:60],
                "content": raw,
                "word_count": len(raw.split()),
                "sections": []
            }

        return result
