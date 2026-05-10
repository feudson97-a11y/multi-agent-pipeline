import os
import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from orchestrator import Orchestrator

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskRequest(BaseModel):
    task: str
    format: str = "markdown"

@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/run")
async def run_pipeline(request: TaskRequest):
    orchestrator = Orchestrator()
    run = await orchestrator.run(request.task, output_format=request.format)
    return {
        "run_id": run.run_id,
        "status": run.status,
        "result": run.final_output
    }

@app.post("/run/stream")
async def run_stream(request: TaskRequest):
    async def generate():
        orchestrator = Orchestrator()

        async def on_event(event_type: str, agent: str, data: dict = {}):
            msg = json.dumps({
                "type": event_type,
                "agent": agent,
                "data": data
            })
            yield f"data: {msg}\n\n"

        agents = ["researcher", "analyst", "writer", "validator"]

        for agent in agents:
            yield f"data: {json.dumps({'type': 'agent_start', 'agent': agent})}\n\n"
            await asyncio.sleep(0.1)

        run = await orchestrator.run(request.task, output_format=request.format)

        for agent in agents:
            yield f"data: {json.dumps({'type': 'agent_done', 'agent': agent})}\n\n"

        result = run.final_output or ""
        if isinstance(result, dict):
            result = result.get("content", json.dumps(result))
        result = result.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(result)
            result = parsed.get("content", result)
        except:
            pass

        words = result.split(" ")
        for i, word in enumerate(words):
            yield f"data: {json.dumps({'type': 'token', 'text': word + ' '})}\n\n"
            if i % 5 == 0:
                await asyncio.sleep(0.03)

        yield f"data: {json.dumps({'type': 'done', 'run_id': run.run_id, 'status': run.status})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")