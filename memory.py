"""
Mémoire partagée entre tous les agents du pipeline.
Backend dict (dev) ou Redis (prod).
"""

import json
import time
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from config import config


@dataclass
class MemoryEntry:
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl: int = 3600

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


class DictMemory:
    """Mémoire en mémoire vive (dev / tests)."""

    def __init__(self):
        self._store: dict[str, MemoryEntry] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        async with self._lock:
            self._store[key] = MemoryEntry(
                value=value,
                ttl=ttl or config.memory.ttl_seconds
            )

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._store[key]
                return None
            return entry.value

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def keys(self, prefix: str = "") -> list[str]:
        async with self._lock:
            return [k for k in self._store if k.startswith(prefix)]

    async def append_to_list(self, key: str, item: Any, max_len: int = None) -> None:
        """Ajoute un item à une liste, en respectant max_len."""
        async with self._lock:
            entry = self._store.get(key)
            lst = entry.value if entry and isinstance(entry.value, list) else []
            lst.append(item)
            if max_len:
                lst = lst[-max_len:]
            self._store[key] = MemoryEntry(value=lst)

    async def clear_all(self) -> None:
        async with self._lock:
            self._store.clear()

    def snapshot(self) -> dict:
        """Retourne un snapshot lisible de l'état actuel."""
        return {
            k: v.value
            for k, v in self._store.items()
            if not v.is_expired()
        }


class SharedMemory:
    """
    Façade unique pour tous les agents.
    
    Namespaces:
      - pipeline:{run_id}:*      état global du run
      - agent:{agent_id}:*       état local d'un agent
      - results:{agent_id}       résultats produits
      - context:*                contexte partagé (tâche, plan, etc.)
    """

    def __init__(self):
        self._backend = DictMemory()

    # --- Contexte global du pipeline ---

    async def set_task(self, run_id: str, task: str) -> None:
        await self._backend.set(f"pipeline:{run_id}:task", task)

    async def get_task(self, run_id: str) -> Optional[str]:
        return await self._backend.get(f"pipeline:{run_id}:task")

    async def set_plan(self, run_id: str, plan: dict) -> None:
        await self._backend.set(f"pipeline:{run_id}:plan", plan)

    async def get_plan(self, run_id: str) -> Optional[dict]:
        return await self._backend.get(f"pipeline:{run_id}:plan")

    async def set_status(self, run_id: str, status: str) -> None:
        await self._backend.set(f"pipeline:{run_id}:status", status)

    async def get_status(self, run_id: str) -> Optional[str]:
        return await self._backend.get(f"pipeline:{run_id}:status")

    # --- Résultats des agents ---

    async def store_result(self, run_id: str, agent_id: str, result: Any) -> None:
        await self._backend.set(f"pipeline:{run_id}:result:{agent_id}", result)
        await self._backend.append_to_list(
            f"pipeline:{run_id}:results_order", agent_id
        )

    async def get_result(self, run_id: str, agent_id: str) -> Optional[Any]:
        return await self._backend.get(f"pipeline:{run_id}:result:{agent_id}")

    async def get_all_results(self, run_id: str) -> dict:
        order = await self._backend.get(f"pipeline:{run_id}:results_order") or []
        results = {}
        for agent_id in order:
            r = await self.get_result(run_id, agent_id)
            if r is not None:
                results[agent_id] = r
        return results

    # --- Historique de conversation par agent ---

    async def add_message(self, run_id: str, agent_id: str, message: dict) -> None:
        await self._backend.append_to_list(
            f"pipeline:{run_id}:history:{agent_id}",
            message,
            max_len=config.memory.max_history
        )

    async def get_history(self, run_id: str, agent_id: str) -> list[dict]:
        return await self._backend.get(
            f"pipeline:{run_id}:history:{agent_id}"
        ) or []

    # --- Contexte partagé (données brutes accessibles à tous) ---

    async def set_context(self, run_id: str, key: str, value: Any) -> None:
        await self._backend.set(f"pipeline:{run_id}:ctx:{key}", value)

    async def get_context(self, run_id: str, key: str) -> Optional[Any]:
        return await self._backend.get(f"pipeline:{run_id}:ctx:{key}")

    # --- Utilitaires ---

    async def clear_run(self, run_id: str) -> None:
        keys = await self._backend.keys(f"pipeline:{run_id}:")
        for k in keys:
            await self._backend.delete(k)

    def snapshot(self) -> dict:
        return self._backend.snapshot()


# Singleton global
shared_memory = SharedMemory()
