from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from geoalchemy2.elements import WKTElement
from app.database import get_db
from app.models import FoodRequest, RequestStatus, UserRole, User
from app.schemas import FoodRequestCreate, FoodRequestOut
from app.core.auth import get_current_user, require_roles

router = APIRouter(prefix="/requests", tags=["Food Requests"])


@router.post("", response_model=FoodRequestOut, status_code=201)
async def create_request(
    payload: FoodRequestCreate,
    current_user: User = Depends(require_roles(UserRole.receiver, UserRole.ngo, UserRole.admin)),
    db: AsyncSession = Depends(get_db)
):
    request = FoodRequest(
        requester_id=current_user.id,
        people_count=payload.people_count,
        urgency=payload.urgency,
        location=WKTElement(f"POINT({payload.lng} {payload.lat})", srid=4326),
        address=payload.address,
        notes=payload.notes,
    )
    db.add(request)
    await db.flush()
    return request


@router.get("", response_model=list[FoodRequestOut])
async def list_requests(
    status: RequestStatus = None,
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(FoodRequest).order_by(FoodRequest.created_at.desc()).limit(limit).offset(offset)
    if status:
        query = query.where(FoodRequest.status == status)
    if current_user.role not in (UserRole.admin, UserRole.ngo, UserRole.volunteer):
        query = query.where(FoodRequest.requester_id == current_user.id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{request_id}", response_model=FoodRequestOut)
async def get_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    req = await db.get(FoodRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@router.delete("/{request_id}", status_code=204)
async def cancel_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    req = await db.get(FoodRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.requester_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    if req.status != RequestStatus.open:
        raise HTTPException(status_code=400, detail="Cannot cancel a matched request")
    req.status = RequestStatus.cancelled
