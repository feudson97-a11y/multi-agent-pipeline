"""
Agent Writer — génération de contenu structuré et formaté.
Transforme les analyses en documents lisibles.
"""

import json
from typing import Any

from agents.base_agent import BaseAgent, AgentTask


SYSTEM_PROMPT = """You are an expert writer agent.

Your mission:
1. Take the raw data and analysis provided
2. Produce a clear, well-structured document in ENGLISH
3. Respect the tone, length and format specified
4. Ensure narrative coherence and readability

Supported formats: markdown, json, plain_text, html, report

Response format (JSON):
{
  "format": "markdown",
  "title": "document title in English",
  "content": "full document content in English",
  "word_count": 0,
  "sections": []
}

Reply ONLY with valid JSON, no markdown or external tags.
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
