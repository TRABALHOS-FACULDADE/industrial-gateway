import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: dict[type, list[Callable]] = {}
        self._pending: dict[str, asyncio.Future] = {}

    def subscribe(self, event_type: type, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Any) -> None:
        for handler in self._subscribers.get(type(event), []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Erro no handler de {type(event).__name__}: {e}")

        # Resolve future pendente, se existir (padrão request-response)
        correlation_id = getattr(event, "correlation_id", None)
        if correlation_id:
            self._resolve(correlation_id, event)

    def expect(self, correlation_id: str) -> asyncio.Future:
        """Registra uma Future para aguardar o evento de resposta desta correlação."""
        future = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future
        return future

    def _resolve(self, correlation_id: str, result: Any) -> None:
        future = self._pending.pop(correlation_id, None)
        if future and not future.done():
            future.set_result(result)
