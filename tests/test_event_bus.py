import pytest
import asyncio
from core.event_bus import EventBus

@pytest.mark.asyncio
async def test_subscribe_and_emit_sync():
    bus = EventBus()
    called_data = []

    def sync_callback(data):
        called_data.append(data)

    bus.subscribe("test_event", sync_callback)
    await bus.emit("test_event", "hello")

    assert called_data == ["hello"]

@pytest.mark.asyncio
async def test_subscribe_and_emit_async():
    bus = EventBus()
    called_data = []

    async def async_callback(data):
        called_data.append(data)

    bus.subscribe("test_event", async_callback)
    await bus.emit("test_event", "world")

    assert called_data == ["world"]

@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    called_data = []

    def callback(data):
        called_data.append(data)

    bus.subscribe("test_event", callback)
    bus.unsubscribe("test_event", callback)
    await bus.emit("test_event", "hello")

    assert called_data == []

@pytest.mark.asyncio
async def test_emit_threadsafe():
    bus = EventBus()
    called_data = []

    def callback(data):
        called_data.append(data)

    bus.subscribe("test_event", callback)
    # Set the loop on the bus
    bus._loop = asyncio.get_running_loop()
    
    # Trigger threadsafe emit
    bus.emit_threadsafe("test_event", "threadsafe")
    
    # Yield control to let the loop run the task
    await asyncio.sleep(0.1)
    assert called_data == ["threadsafe"]
