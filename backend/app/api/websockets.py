from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.websocket import ws_manager
from app.core.auth import decode_token

router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws")
async def global_feed(websocket: WebSocket, token: str = Query(None)):
    """Global activity feed — all authenticated users."""
    user_id = None
    if token:
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
        except Exception:
            await websocket.close(code=4001)
            return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@router.websocket("/ws/delivery/{delivery_id}")
async def delivery_room(
    websocket: WebSocket,
    delivery_id: str,
    token: str = Query(None)
):
    """Per-delivery room for real-time status updates."""
    if token:
        try:
            decode_token(token)
        except Exception:
            await websocket.close(code=4001)
            return

    room_id = delivery_id
    await ws_manager.connect(websocket, room_id=room_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room_id=room_id)


@router.websocket("/ws/user/{user_id}")
async def user_room(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(None)
):
    """Per-user room for personal notifications."""
    if token:
        try:
            payload = decode_token(token)
            if payload.get("sub") != user_id:
                await websocket.close(code=4003)
                return
        except Exception:
            await websocket.close(code=4001)
            return

    room_id = f"user:{user_id}"
    await ws_manager.connect(websocket, room_id=room_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room_id=room_id)
