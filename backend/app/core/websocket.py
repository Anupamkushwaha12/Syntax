"""
WebSocket connection manager for real-time updates.
Supports per-user rooms and global broadcast.
"""
import json
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._global: Set[WebSocket] = set()
        self._rooms: Dict[str, Set[WebSocket]] = {}  # room_id → sockets

    async def connect(self, ws: WebSocket, room_id: str = None):
        await ws.accept()
        self._global.add(ws)
        if room_id:
            self._rooms.setdefault(room_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, room_id: str = None):
        self._global.discard(ws)
        if room_id and room_id in self._rooms:
            self._rooms[room_id].discard(ws)

    async def broadcast(self, data: dict):
        """Send to all connected clients."""
        message = json.dumps(data)
        dead = set()
        for ws in list(self._global):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._global -= dead

    async def send_to_room(self, room_id: str, data: dict):
        """Send to all clients in a specific room (e.g., delivery_id)."""
        message = json.dumps(data)
        if room_id not in self._rooms:
            return
        dead = set()
        for ws in list(self._rooms[room_id]):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._rooms[room_id] -= dead

    async def send_to_user(self, user_id: str, data: dict):
        await self.send_to_room(f"user:{user_id}", data)


ws_manager = ConnectionManager()
