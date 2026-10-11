# Pipeline Multi-Agents — Python + Claude

Pipeline d'automatisation agentique avec 4 agents spécialisés qui collaborent pour accomplir des tâches complexes.

## Architecture

```
Entrée utilisateur
       │
       ▼
  Orchestrateur  ──── planifie et dispatche ────►  Mémoire partagée
       │                                                  ▲
       ├──► Researcher  (web search, collecte)            │
       ├──► Analyst     (analyse, calculs)                │  tous les agents
       ├──► Writer      (rédaction, formatage)            │  lisent/écrivent
       └──► Validator   (QA, retry si besoin)             │
                                                          │
       Bus d'événements (asyncio) ─────────────────────────
```

## Agents

| Agent | Rôle | Outils |
|---|---|---|
| **Researcher** | Recherche web, collecte d'informations | `web_search` (Anthropic natif) |
| **Analyst** | Analyse, raisonnement, calculs | `execute_python` (sandbox) |
| **Writer** | Rédaction, formatage du document final | — |
| **Validator** | Contrôle qualité, décision retry | — |

## Installation

```bash
# Cloner le dépôt
git clone https://github.com/feudson97-a11y/multi-agent-pipeline.git
cd multi-agent-pipeline

# Installer les dépendances (Python 3.11+)
pip install -r requirements.txt

# Configurer la clé API
export ANTHROPIC_API_KEY=sk-ant-...
```

## Utilisation

```bash
# Tâche simple
python main.py "Analyse les tendances du marché de l'IA en 2025"

# Avec format de sortie et sauvegarde
python main.py "Rapport Python vs Go pour le backend" --format report --save

# Mode interactif
python main.py --interactive
```

## Formats de sortie

- `markdown` — document Markdown (défaut)
- `report` — rapport structuré avec sections
- `json` — données structurées JSON
- `plain_text` — texte brut
- `html` — page HTML

## Structure du projet

```
multi-agent-pipeline/
├── main.py              # Point d'entrée CLI
├── config.py            # Configuration centralisée
├── orchestrator.py      # Planification + dispatch
├── memory.py            # État partagé entre agents
├── event_bus.py         # Coordination asynchrone
├── requirements.txt
└── agents/
    ├── __init__.py
    ├── base_agent.py    # Classe abstraite commune
    ├── researcher.py    # Recherche web
    ├── analyst.py       # Analyse + exec Python
    ├── writer.py        # Génération de contenu
    └── validator.py     # Contrôle qualité
```

## Personnalisation

### Ajouter un agent

```python
# agents/my_agent.py
from agents.base_agent import BaseAgent, AgentTask

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="my_agent",
            system_prompt="Tu es un expert en..."
        )
    
    async def run(self, task: AgentTask) -> dict:
        messages = [{"role": "user", "content": task.instruction}]
        result = await self.call_claude(messages)
        return {"output": result}
```

```python
# Dans orchestrator.py, ajouter à self._agents:
self._agents["my_agent"] = MyAgent()
```

### Ajouter un outil

```python
MY_TOOL = {
    "name": "my_tool",
    "description": "Fait quelque chose d'utile",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "La requête"}
        },
        "required": ["query"]
    }
}

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(...)
        self.tools = [MY_TOOL]
    
    async def _execute_tool(self, tool_name: str, tool_input: dict):
        if tool_name == "my_tool":
            # logique ici
            return "résultat"
```

### Passer en Redis (production)

```python
# config.py
memory = MemoryConfig(backend="redis", redis_url="redis://localhost:6379/0")
```

Puis dans `memory.py`, remplacer `DictMemory` par une implémentation Redis avec `aioredis`.

## Variables d'environnement

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Clé API Anthropic |

## Modèle utilisé

`claude-haiku-4-5-20251001` — modifiable dans `config.py` → `AgentConfig.model`
