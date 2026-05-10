"""
Bus d'événements asynchrone basé sur asyncio.
Permet aux agents de communiquer sans couplage direct.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from enum import Enum


class EventType(str, Enum):
    # Cycle de vie du pipeline
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"

    # Cycle de vie des agents
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_RETRY = "agent.retry"

    # Tâches
    TASK_ASSIGNED = "task.assigned"
    TASK_RESULT = "task.result"
    TASK_VALIDATION_PASSED = "task.validation.passed"
    TASK_VALIDATION_FAILED = "task.validation.failed"

    # Données intermédiaires
    DATA_AVAILABLE = "data.available"
    CONTEXT_UPDATED = "context.updated"


@dataclass
class Event:
    type: EventType
    run_id: str
    source: str                          # agent_id ou "orchestrator"
    payload: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def __repr__(self):
        return f"Event({self.type} | {self.source} | run={self.run_id[:8]})"


Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Bus pub/sub in-process.
    
    Usage:
        bus = EventBus()
        
        @bus.on(EventType.AGENT_COMPLETED)
        async def handle(event: Event):
            print(f"Agent terminé: {event.source}")
        
        await bus.publish(Event(type=EventType.AGENT_COMPLETED, ...))
    """

    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = {}
        self._wildcard_handlers: list[Handler] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._history: list[Event] = []
        self._running = False

    def on(self, event_type: EventType):
        """Décorateur pour s'abonner à un type d'événement."""
        def decorator(fn: Handler):
            self._handlers.setdefault(event_type, []).append(fn)
            return fn
        return decorator

    def on_any(self, fn: Handler):
        """S'abonner à tous les événements (observabilité)."""
        self._wildcard_handlers.append(fn)
        return fn

    async def publish(self, event: Event) -> None:
        """Publie un événement dans la queue."""
        await self._queue.put(event)

    async def _dispatch(self, event: Event) -> None:
        """Dispatche un événement à tous les handlers enregistrés."""
        self._history.append(event)

        handlers = self._handlers.get(event.type, []) + self._wildcard_handlers
        if not handlers:
            return

        results = await asyncio.gather(
            *[h(event) for h in handlers],
            return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                print(f"[EventBus] Erreur dans handler pour {event.type}: {r}")

    async def start(self) -> None:
        """Démarre la boucle de dispatch en arrière-plan."""
        self._running = True
        asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[EventBus] Erreur boucle: {e}")

    async def stop(self) -> None:
        """Arrête proprement le bus après drain de la queue."""
        await self._queue.join()
        self._running = False

    async def wait_for(
        self,
        event_type: EventType,
        run_id: str,
        timeout: float = 60.0
    ) -> Event:
        """Attend un événement spécifique (utile pour synchronisation)."""
        future: asyncio.Future[Event] = asyncio.get_event_loop().create_future()

        async def _resolver(event: Event):
            if event.run_id == run_id and not future.done():
                future.set_result(event)

        self._handlers.setdefault(event_type, []).append(_resolver)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._handlers[event_type].remove(_resolver)

    def get_history(self, run_id: str = None) -> list[Event]:
        if run_id:
            return [e for e in self._history if e.run_id == run_id]
        return list(self._history)


# Singleton global
event_bus = EventBus()
