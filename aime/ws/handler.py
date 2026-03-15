"""WebSocket handler for the MUD terminal."""

import asyncio
import json
import traceback

from fastapi import WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.core.daily_cycle import DailyCycle
from aime.core.entity_mind import EntityMind
from aime.core.feed_processor import process_feed
from aime.core.llm import get_llm
from aime.core.memory_layer import MemoryLayer
from aime.core.social_engine import SocialEngine
from aime.deps import async_session, get_chroma
from aime.models.daily_log import DailyLog
from aime.models.entity import Entity
from aime.models.player import Player
from aime.ws.commands import parse_command
from aime.ws.renderer import (
    divider,
    entity_speech,
    error_msg,
    highlight,
    narrative,
    render_help,
    render_leaderboard,
    render_status,
    system_msg,
)

# Keepalive ping interval in seconds
WS_PING_INTERVAL = 30

WELCOME_ART = r"""
╔══════════════════════════════════════════════════╗
║                                                  ║
║     █████╗ ██╗   ███╗   ███╗███████╗            ║
║    ██╔══██╗██║   ████╗ ████║██╔════╝            ║
║    ███████║██║   ██╔████╔██║█████╗              ║
║    ██╔══██║██║   ██║╚██╔╝██║██╔══╝              ║
║    ██║  ██║██║██╗██║ ╚═╝ ██║███████╗            ║
║    ╚═╝  ╚═╝╚═╝╚═╝╚═╝     ╚═╝╚══════╝            ║
║                                                  ║
║        念 体 修 炼 · AI Cultivation World        ║
║                                                  ║
║   输入 "帮助" 查看命令  |  Type "help" for cmds  ║
║                                                  ║
╚══════════════════════════════════════════════════╝
"""


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, player_id: str, ws: WebSocket):
        await ws.accept()
        self.active[player_id] = ws

    def disconnect(self, player_id: str):
        self.active.pop(player_id, None)

    async def send(self, player_id: str, message: str):
        ws = self.active.get(player_id)
        if ws:
            await ws.send_text(message)


manager = ConnectionManager()


async def _keepalive(websocket: WebSocket, player_id: str):
    """Send periodic ping to keep connection alive."""
    try:
        while True:
            await asyncio.sleep(WS_PING_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                break
    except asyncio.CancelledError:
        pass


async def ws_endpoint(websocket: WebSocket):
    """Main WebSocket handler for MUD terminal."""
    # Auth via query param
    token = websocket.query_params.get("token", "")
    player_id = _verify_token(token)
    if not player_id:
        await websocket.close(code=4001, reason="认证失败")
        return

    # Verify player still exists in DB (handles Render ephemeral FS restarts)
    async with async_session() as db:
        result = await db.execute(select(Player).where(Player.id == player_id))
        if not result.scalar_one_or_none():
            await websocket.close(code=4002, reason="账号不存在，请重新注册")
            return

    await manager.connect(player_id, websocket)
    await websocket.send_text(system_msg(WELCOME_ART))

    # Start keepalive ping task
    ping_task = asyncio.create_task(_keepalive(websocket, player_id))

    # Session state
    feed_buffer: list[str] = []
    feed_mode = False
    session_id: str | None = None

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
                # Ignore pong responses from client
                if data.get("type") == "pong":
                    continue
                text = data.get("cmd", data.get("text", "")).strip()
            except json.JSONDecodeError:
                text = raw.strip()

            if not text:
                continue

            # Feed mode: collect multi-line input
            if feed_mode:
                if text == "//end":
                    feed_mode = False
                    full_text = "\n".join(feed_buffer)
                    feed_buffer.clear()
                    if full_text.strip():
                        await _handle_feed(player_id, websocket, full_text)
                    else:
                        await websocket.send_text(error_msg("投喂内容为空"))
                else:
                    feed_buffer.append(text)
                    await websocket.send_text(
                        system_msg(f"  [{len(feed_buffer)} 行已录入，输入 //end 结束]")
                    )
                continue

            # Parse command
            handler, args = parse_command(text)

            if handler == "feed":
                if args:
                    await _handle_feed(player_id, websocket, args)
                else:
                    feed_mode = True
                    feed_buffer.clear()
                    await websocket.send_text(
                        system_msg("进入投喂模式。逐行输入内容，输入 //end 完成投喂。")
                    )
            elif handler == "dialogue":
                if not args:
                    await websocket.send_text(error_msg("请输入对话内容：对话 <你想说的话>"))
                else:
                    session_id = await _handle_dialogue(
                        player_id, websocket, args, session_id
                    )
            elif handler == "view_status":
                await _handle_status(player_id, websocket)
            elif handler == "view_log":
                await _handle_log(player_id, websocket, args)
            elif handler == "view_leaderboard":
                await _handle_leaderboard(player_id, websocket)
            elif handler == "set_direction":
                if not args:
                    await websocket.send_text(
                        error_msg("请输入方向：设定方向 <修炼方向>")
                    )
                else:
                    await _handle_set_direction(player_id, websocket, args)
            elif handler == "lun_dao":
                await _handle_social(player_id, websocket, "lun_dao")
            elif handler == "qie_cuo":
                await _handle_social(player_id, websocket, "qie_cuo")
            elif handler == "help":
                await websocket.send_text(narrative(render_help()))
            elif handler == "unknown":
                await websocket.send_text(
                    error_msg(f"未知命令：{args}。输入 帮助 查看可用命令。")
                )

    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        manager.disconnect(player_id)


def _verify_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


async def _get_entity(player_id: str, db: AsyncSession) -> Entity | None:
    result = await db.execute(
        select(Entity).where(Entity.player_id == player_id)
    )
    return result.scalar_one_or_none()


async def _handle_feed(player_id: str, ws: WebSocket, text: str):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体，请先通过 API 创建。"))
            return
        try:
            feed = await process_feed(entity, text, None, db)
            await ws.send_text(
                highlight(f"念体已接收投喂。解析为 {feed.chunk_count} 个记忆碎片。")
            )
        except Exception as e:
            await ws.send_text(error_msg(f"投喂失败：{e}"))


async def _handle_dialogue(
    player_id: str, ws: WebSocket, message: str, session_id: str | None
) -> str | None:
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体。"))
            return session_id

        memory = MemoryLayer(get_chroma())
        mind = EntityMind(memory, get_llm())

        await ws.send_text(entity_speech("", streaming=True, done=False))

        try:
            full = ""
            current_session = session_id
            async for token in mind.dialogue(entity, message, db, current_session):
                full += token
                await ws.send_text(
                    entity_speech(token, streaming=True, done=False)
                )
            await ws.send_text(entity_speech("", streaming=True, done=True))

            # Get the session_id from saved turns
            if current_session is None:
                from aime.utils.id_gen import gen_short_id
                current_session = gen_short_id()
            return current_session
        except Exception as e:
            await ws.send_text(error_msg(f"对话失败：{e}"))
            return session_id


async def _handle_status(player_id: str, ws: WebSocket):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体。"))
            return

        # Query social event stats
        from sqlalchemy import func, or_, case
        from aime.models.social_event import SocialEvent

        social_stats = await db.execute(
            select(
                SocialEvent.event_type,
                func.count().label("count"),
            )
            .where(
                or_(
                    SocialEvent.entity_a_id == entity.id,
                    SocialEvent.entity_b_id == entity.id,
                )
            )
            .group_by(SocialEvent.event_type)
        )
        event_counts = {row[0]: row[1] for row in social_stats.all()}

        # Query qie_cuo wins
        qie_cuo_events = await db.execute(
            select(SocialEvent)
            .where(
                SocialEvent.event_type == "qie_cuo",
                or_(
                    SocialEvent.entity_a_id == entity.id,
                    SocialEvent.entity_b_id == entity.id,
                ),
            )
        )
        wins = 0
        losses = 0
        for evt in qie_cuo_events.scalars().all():
            try:
                outcome = json.loads(evt.outcome) if evt.outcome else {}
                winner = outcome.get("winner", "")
                if winner == entity.name:
                    wins += 1
                else:
                    losses += 1
            except (json.JSONDecodeError, TypeError):
                pass

        # Recent social events (last 5)
        recent_social = await db.execute(
            select(SocialEvent)
            .where(
                or_(
                    SocialEvent.entity_a_id == entity.id,
                    SocialEvent.entity_b_id == entity.id,
                )
            )
            .order_by(SocialEvent.created_at.desc())
            .limit(5)
        )
        recent_events = []
        for evt in recent_social.scalars().all():
            opponent_id = evt.entity_b_id if evt.entity_a_id == entity.id else evt.entity_a_id
            opp_result = await db.execute(select(Entity.name).where(Entity.id == opponent_id))
            opp_name = opp_result.scalar_one_or_none() or "未知"
            outcome_str = ""
            if evt.event_type == "qie_cuo" and evt.outcome:
                try:
                    o = json.loads(evt.outcome)
                    outcome_str = f" → {'胜' if o.get('winner') == entity.name else '负'}"
                except (json.JSONDecodeError, TypeError):
                    pass
            event_label = "论道" if evt.event_type == "lun_dao" else "切磋"
            recent_events.append(f"{event_label} vs {opp_name}{outcome_str}（{evt.topic or '未知'}）")

        status_data = {
            "name": entity.name,
            "core_belief": entity.core_belief,
            "intent": entity.intent,
            "current_direction": entity.current_direction,
            "cultivation_day": entity.cultivation_day,
            "total_feeds": entity.total_feeds,
            "total_dialogues": entity.total_dialogues,
            "soul_force": entity.soul_force,
            "fusion": {
                "alignment": entity.fusion_alignment,
                "depth": entity.fusion_depth,
                "coherence": entity.fusion_coherence,
                "integrity": entity.fusion_integrity,
                "total": entity.fusion_total,
            },
            "social": {
                "lun_dao_count": event_counts.get("lun_dao", 0),
                "qie_cuo_count": event_counts.get("qie_cuo", 0),
                "wins": wins,
                "losses": losses,
                "recent": recent_events,
            },
        }
        await ws.send_text(narrative(render_status(status_data)))


async def _handle_log(player_id: str, ws: WebSocket, args: str):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体。"))
            return

        query = select(DailyLog).where(DailyLog.entity_id == entity.id)
        if args.strip().isdigit():
            day = int(args.strip())
            query = query.where(DailyLog.day == day)
        else:
            query = query.order_by(DailyLog.day.desc()).limit(1)

        result = await db.execute(query)
        log = result.scalar_one_or_none()
        if not log:
            await ws.send_text(system_msg("暂无修炼日志。可能需要等待每日结算。"))
            return

        await ws.send_text(narrative(log.content))


async def _handle_leaderboard(player_id: str, ws: WebSocket):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        result = await db.execute(
            select(Entity).order_by(Entity.fusion_total.desc()).limit(20)
        )
        entities = list(result.scalars().all())

        entries = []
        for e in entities:
            entries.append({
                "name": e.name,
                "current_direction": e.current_direction,
                "fusion_total": e.fusion_total,
                "soul_force": e.soul_force,
                "is_self": entity and e.id == entity.id,
            })

        await ws.send_text(narrative(render_leaderboard(entries)))


async def _handle_set_direction(player_id: str, ws: WebSocket, direction: str):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体。"))
            return
        entity.current_direction = direction
        await db.commit()
        await ws.send_text(highlight(f"修炼方向已设定为：{direction}"))


async def _handle_social(player_id: str, ws: WebSocket, event_type: str):
    async with async_session() as db:
        entity = await _get_entity(player_id, db)
        if not entity:
            await ws.send_text(error_msg("你还没有念体。"))
            return

        memory = MemoryLayer(get_chroma())
        social = SocialEngine(memory, get_llm())

        opponent = await social.find_opponent(entity, db)
        if not opponent:
            await ws.send_text(error_msg("世界中暂无其他念体可以交流。"))
            return

        event_name = "论道" if event_type == "lun_dao" else "切磋"
        await ws.send_text(
            system_msg(f"正在与「{opponent.name}」进行{event_name}...")
        )

        try:
            if event_type == "lun_dao":
                event = await social.run_lun_dao(entity, opponent, db)
            else:
                event = await social.run_qie_cuo(entity, opponent, db)

            await ws.send_text(divider())
            await ws.send_text(
                highlight(f"━━━ {event_name}记录 · 与「{opponent.name}」 ━━━")
            )
            await ws.send_text(narrative(f"话题：{event.topic}"))
            await ws.send_text(narrative(event.transcript))
            if event.outcome:
                await ws.send_text(highlight(f"\n结果：{event.outcome}"))
            await ws.send_text(divider())
        except Exception as e:
            await ws.send_text(error_msg(f"{event_name}失败：{e}"))
            traceback.print_exc()
