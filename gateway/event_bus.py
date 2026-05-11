import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None]]


class EventBus:
    def __init__(self, max_queue_size: int = 0):
        self._subscribers: dict[type, list[EventHandler]] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="event-bus-worker")
        logger.info("EventBus iniciado.")

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        await self._queue.join()

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        self._cancel_pending("EventBus encerrado antes da resposta.")
        logger.info("EventBus encerrado.")

    async def publish(self, event: Any) -> None:
        if not self._running:
            raise RuntimeError("EventBus precisa ser iniciado antes de publicar eventos.")
        await self._queue.put(event)

    def expect(self, correlation_id: str) -> asyncio.Future:
        future = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future
        return future

    def cancel_expectation(self, correlation_id: str) -> None:
        future = self._pending.pop(correlation_id, None)
        if future and not future.done():
            future.cancel()

    async def _worker(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self._dispatch(event)
            finally:
                self._queue.task_done()

    async def _dispatch(self, event: Any) -> None:
        handlers = self._subscribers.get(type(event), [])
        if handlers:
            results = await asyncio.gather(
                *(handler(event) for handler in handlers),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    logger.error(
                        f"Erro no handler de {type(event).__name__}: {result}",
                        exc_info=result,
                    )

        correlation_id = getattr(event, "correlation_id", None)
        if correlation_id and self._is_response_event(event):
            self._resolve(correlation_id, event)

    def _resolve(self, correlation_id: str, result: Any) -> None:
        future = self._pending.pop(correlation_id, None)
        if future and not future.done():
            future.set_result(result)

    def _is_response_event(self, event: Any) -> bool:
        return hasattr(event, "success")

    def _cancel_pending(self, message: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RuntimeError(message))
        self._pending.clear()
