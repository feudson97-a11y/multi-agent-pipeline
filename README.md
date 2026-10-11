# Multi-Agent Pipeline — Python + Claude

An agentic automation pipeline in which 4 specialized agents collaborate to complete complex tasks.

## Architecture

```
User input
       │
       ▼
  Orchestrator  ──── plans and dispatches ────►  Shared memory
       │                                                  ▲
       ├──► Researcher  (web search, data gathering)      │
       ├──► Analyst     (analysis, calculations)          │  all agents
       ├──► Writer      (writing, formatting)             │  read/write
       └──► Validator   (QA, retry if needed)             │
                                                          │
       Event bus (asyncio) ────────────────────────────────
```

## Agents

| Agent | Role | Tools |
|---|---|---|
| **Researcher** | Web search, information gathering | `web_search` (native Anthropic tool) |
| **Analyst** | Analysis, reasoning, calculations | `execute_python` (sandbox) |
| **Writer** | Writing and formatting the final document | — |
| **Validator** | Quality control, retry decision | — |

## Installation

```bash
# Clone the repository
git clone https://github.com/feudson97-a11y/multi-agent-pipeline.git
cd multi-agent-pipeline

# Install dependencies (Python 3.11+)
pip install -r requirements.txt

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# Simple task
python main.py "Analyze AI market trends in 2025"

# With output format and saving
python main.py "Python vs Go report for backend development" --format report --save

# Interactive mode
python main.py --interactive
```

## Output formats

- `markdown` — Markdown document (default)
- `report` — structured report with sections
- `json` — structured JSON data
- `plain_text` — plain text
- `html` — HTML page

## Project structure

```
multi-agent-pipeline/
├── main.py              # CLI entry point
├── config.py            # Centralized configuration
├── orchestrator.py      # Planning + dispatch
├── memory.py            # State shared between agents
├── event_bus.py         # Asynchronous coordination
├── requirements.txt
└── agents/
    ├── __init__.py
    ├── base_agent.py    # Shared abstract base class
    ├── researcher.py    # Web research
    ├── analyst.py       # Analysis + Python execution
    ├── writer.py        # Content generation
    └── validator.py     # Quality control
```

## Customization

### Add an agent

```python
# agents/my_agent.py
from agents.base_agent import BaseAgent, AgentTask

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="my_agent",
            system_prompt="You are an expert in..."
        )
    
    async def run(self, task: AgentTask) -> dict:
        messages = [{"role": "user", "content": task.instruction}]
        result = await self.call_claude(messages)
        return {"output": result}
```

```python
# In orchestrator.py, add it to self._agents:
self._agents["my_agent"] = MyAgent()
```

### Add a tool

```python
MY_TOOL = {
    "name": "my_tool",
    "description": "Does something useful",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The query"}
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
            # your logic here
            return "result"
```

### Switch to Redis (production)

```python
# config.py
memory = MemoryConfig(backend="redis", redis_url="redis://localhost:6379/0")
```

Then, in `memory.py`, replace `DictMemory` with a Redis implementation using `aioredis`.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | — | Anthropic API key |

## Model

`claude-haiku-4-5-20251001` — configurable in `config.py` → `AgentConfig.model`
