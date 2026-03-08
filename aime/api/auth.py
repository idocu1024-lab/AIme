from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.deps import get_current_player, get_db
from aime.models.player import Player
from aime.schemas.player import PlayerInfo, PlayerLogin, PlayerRegister, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(player_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": player_id, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/register", response_model=TokenResponse)
async def register(data: PlayerRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(Player).where(Player.username == data.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    player = Player(
        username=data.username,
        password_hash=_hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return TokenResponse(access_token=_create_token(player.id))


@router.post("/login", response_model=TokenResponse)
async def login(data: PlayerLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Player).where(Player.username == data.username)
    )
    player = result.scalar_one_or_none()
    if not player or not _verify_password(data.password, player.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(access_token=_create_token(player.id))


@router.get("/me", response_model=PlayerInfo)
async def me(player: Player = Depends(get_current_player)):
    return PlayerInfo(
        id=player.id,
        username=player.username,
        display_name=player.display_name,
        has_entity=player.entity is not None,
    )
