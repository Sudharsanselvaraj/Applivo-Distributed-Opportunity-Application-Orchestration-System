"""
app/api/routes/auth.py
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas import LoginRequest, TokenData, TokenResponse, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def hash_password(password: str) -> str:
    # bcrypt has a maximum password length of 72 bytes
    # Truncate if necessary
    return pwd_context.hash(password[:72])

def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt has a maximum password length of 72 bytes
    # Truncate if necessary
    return pwd_context.verify(plain[:72], hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=user_id, email=payload.get("email", ""))
    except JWTError:
        raise credentials_exception
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()
    from app.models.user import UserProfile
    # Sync settings from .env to UserProfile for agent automation
    profile = UserProfile(
        user_id=user.id,
        # Auto apply settings from .env
        auto_apply_enabled=settings.AUTO_APPLY_ENABLED,
        auto_apply_threshold=settings.AUTO_APPLY_MATCH_THRESHOLD,
        auto_apply_daily_limit=settings.AUTO_APPLY_DAILY_LIMIT,
        require_apply_approval=settings.AUTO_APPLY_REQUIRE_APPROVAL,
        # User info from .env
        phone=settings.USER_PHONE,
        location=settings.USER_LOCATION,
        # Notification settings - enable Telegram by default if token exists
        notify_via_telegram=bool(settings.TELEGRAM_BOT_TOKEN),
        notify_via_email=bool(settings.SMTP_USERNAME),
        notification_email=settings.USER_EMAIL or settings.SMTP_USERNAME,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    
    # Send welcome notification
    try:
        from app.services.notification_service import NotificationService
        notif_service = NotificationService()
        await notif_service.notify(
            title="Welcome to AI Career Platform! 🎉",
            body=f"Hi {payload.full_name}!\n\nWelcome to your AI-powered career assistant. Here's what you can do:\n\n• Set up your profile with skills & experience\n• Upload your resume for AI-powered tailoring\n• Connect platform credentials for auto-apply\n• Let AI find and apply to jobs for you\n\nGet started at: /dashboard\n\nBest,\nThe AI Career Team",
            event_type="user_welcome"
        )
    except Exception as e:
        # Log but don't fail registration if notification fails
        import structlog
        logger = structlog.get_logger()
        logger.warning("Welcome notification failed", error=str(e))
    
    return user

@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is disabled")
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token({"sub": user.id, "email": user.email})
    return TokenResponse(access_token=token, expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token({"sub": user.id, "email": user.email})
    return TokenResponse(access_token=token, expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)

@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
