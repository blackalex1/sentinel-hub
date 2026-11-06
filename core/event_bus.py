import asyncio
import logging
import inspect
from typing import Callable, Dict, List, Any

logger = logging.getLogger("EventBus")

class EventBus:
    """
    Асинхронная шина событий. 
    Плагины и ядро общаются через нее, не зная друг о друге (развязка).
    """
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._loop = None

    def subscribe(self, event_name: str, callback: Callable):
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        if callback not in self._subscribers[event_name]:
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable):
        if event_name in self._subscribers and callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)

    async def emit(self, event_name: str, data: Any = None):
        """Асинхронно вызывает все коллбэки, подписанные на событие"""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
            
        if event_name in self._subscribers:
            callbacks = self._subscribers[event_name]
            for callback in callbacks:
                try:
                    if inspect.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Error in event handler for {event_name}: {e}")

    def emit_threadsafe(self, event_name: str, data: Any = None):
        """Потокобезопасная версия emit для вызова из других потоков (например, GUI)"""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.emit(event_name, data), self._loop)
        else:
            # Если цикл еще не захвачен, пробуем найти его (но это ненадежно)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.emit(event_name, data), loop)
            except:
                pass

# Global instance
event_bus = EventBus()
