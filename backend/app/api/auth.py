from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import User, ActivityLog, ActivityType
from app.schemas import RegisterRequest, LoginRequest, TokenResponse, UserOut, VolunteerStatusUpdate
from app.core.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    get_current_user, require_roles
)
from app.models import UserRole
from geoalchemy2.elements import WKTElement

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    location = None
    if payload.lat is not None and payload.lng is not None:
        location = WKTElement(f"POINT({payload.lng} {payload.lat})", srid=4326)

    user = User(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        location=location,
        address=payload.address,
        vehicle_type=payload.vehicle_type,
    )
    db.add(user)

    log = ActivityLog(
        activity_type=ActivityType.user_registered,
        message=f"New {payload.role.value} registered: {payload.name}",
        location_name=payload.address
    )
    db.add(log)
    await db.flush()

    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(
        access_token=create_access_token(user.id, user.role.value),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/availability", response_model=UserOut)
async def update_availability(
    payload: VolunteerStatusUpdate,
    current_user: User = Depends(require_roles(UserRole.volunteer)),
    db: AsyncSession = Depends(get_db)
):
    current_user.is_available = payload.is_available
    return current_user
