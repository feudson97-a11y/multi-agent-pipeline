"""
Agent Analyst — analyse, raisonnement structuré, exécution de code.
Prend les données brutes du Researcher et en tire des insights.
"""

import json
import ast
import io
import contextlib
from typing import Any

from agents.base_agent import BaseAgent, AgentTask


SYSTEM_PROMPT = """Tu es un agent analyste expert en données et raisonnement structuré.

Ta mission :
1. Analyser les informations brutes fournies (résultats de recherche, données, texte)
2. Identifier les patterns, tendances et insights clés
3. Produire une analyse structurée avec des conclusions actionnables
4. Si nécessaire, utiliser l'outil execute_python pour des calculs ou transformations

Format de réponse attendu (JSON) :
{
  "insights": ["insight 1", "insight 2", ...],
  "patterns": ["pattern observé 1", ...],
  "conclusions": "analyse narrative complète",
  "recommendations": ["recommandation 1", ...],
  "confidence": 0.0-1.0,
  "data_quality": "high|medium|low",
  "code_outputs": {}  // résultats des exécutions Python si applicable
}

Réponds UNIQUEMENT avec du JSON valide, sans markdown ni balises.
"""

EXECUTE_PYTHON_TOOL = {
    "name": "execute_python",
    "description": (
        "Exécute du code Python pour analyser des données. "
        "Utile pour calculs statistiques, transformations, agrégations. "
        "Retourne stdout comme résultat."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Code Python à exécuter (pas de librairies externes)"
            }
        },
        "required": ["code"]
    }
}


class AnalystAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            agent_id="analyst",
            system_prompt=SYSTEM_PROMPT
        )
        self.tools = [EXECUTE_PYTHON_TOOL]
        self._code_outputs: dict = {}

    async def run(self, task: AgentTask) -> dict:
        """
        Analyse les données fournies ou les résultats du Researcher.
        """
        # Récupère les résultats des agents précédents
        prev = await self.get_previous_results(task)

        # Construit le message d'analyse
        data_to_analyze = json.dumps(prev, ensure_ascii=False, indent=2) if prev else ""
        instruction_context = json.dumps(task.context, ensure_ascii=False)

        messages = [
            {
                "role": "user",
                "content": (
                    f"Tâche d'analyse: {task.instruction}\n\n"
                    f"Données à analyser:\n{data_to_analyze}\n\n"
                    f"Contexte additionnel: {instruction_context}"
                )
            }
        ]

        raw = await self.call_claude(messages)

        try:
            clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
            result = json.loads(clean)
        except json.JSONDecodeError:
            result = {
                "insights": [],
                "patterns": [],
                "conclusions": raw,
                "recommendations": [],
                "confidence": 0.5,
                "data_quality": "medium",
                "code_outputs": self._code_outputs
            }

        result["code_outputs"] = self._code_outputs
        return result

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """Exécute du code Python dans un sandbox minimal."""
        if tool_name == "execute_python":
            return self._run_python_safe(tool_input.get("code", ""))
        raise NotImplementedError(f"Outil inconnu: {tool_name}")

    def _run_python_safe(self, code: str) -> str:
        """
        Exécute du Python dans un contexte restreint.
        Capture stdout et retourne le résultat.
        """
        allowed_builtins = {
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "sum", "min", "max", "abs", "round", "int", "float",
            "str", "list", "dict", "set", "tuple", "bool", "type",
            "isinstance", "hasattr", "getattr", "repr"
        }

        safe_globals = {
            "__builtins__": {k: __builtins__[k] for k in allowed_builtins if k in __builtins__}
            if isinstance(__builtins__, dict)
            else {k: getattr(__builtins__, k) for k in allowed_builtins if hasattr(__builtins__, k)},
            "json": json,
        }

        stdout_capture = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(compile(code, "<agent>", "exec"), safe_globals)
            output = stdout_capture.getvalue()
            self._code_outputs[f"exec_{len(self._code_outputs)}"] = output
            return output or "Exécuté sans sortie."
        except Exception as e:
            error_msg = f"Erreur d'exécution: {type(e).__name__}: {e}"
            self._code_outputs[f"error_{len(self._code_outputs)}"] = error_msg
            return error_msg
