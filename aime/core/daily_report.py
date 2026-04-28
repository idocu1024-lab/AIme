"""Compose and send the daily cultivation report email."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aime.config import settings
from aime.deps import async_session
from aime.models.daily_log import DailyLog
from aime.models.entity import Entity
from aime.models.player import Player
from aime.models.social_event import SocialEvent
from aime.utils.email_sender import send_email

logger = logging.getLogger("aime.daily_report")


async def _gather_data(player: Player, db: AsyncSession) -> dict | None:
    """Collect everything needed for one player's daily report."""
    if not player.entity:
        return None
    entity = player.entity

    # Latest daily log (just-generated)
    log_result = await db.execute(
        select(DailyLog)
        .where(DailyLog.entity_id == entity.id)
        .order_by(DailyLog.day.desc())
        .limit(1)
    )
    latest_log = log_result.scalar_one_or_none()

    # Today's social events (events whose day matches the just-completed day)
    target_day = latest_log.day if latest_log else entity.cultivation_day - 1
    social_result = await db.execute(
        select(SocialEvent)
        .where(
            SocialEvent.day == target_day,
            or_(
                SocialEvent.entity_a_id == entity.id,
                SocialEvent.entity_b_id == entity.id,
            ),
        )
        .order_by(SocialEvent.created_at.asc())
    )
    social_events = list(social_result.scalars().all())

    # Resolve opponent names
    enriched = []
    for evt in social_events:
        opp_id = (
            evt.entity_b_id if evt.entity_a_id == entity.id else evt.entity_a_id
        )
        opp_result = await db.execute(
            select(Entity.name).where(Entity.id == opp_id)
        )
        opp_name = opp_result.scalar_one_or_none() or "未知"

        # Extract a short summary
        summary = ""
        outcome = {}
        try:
            outcome = json.loads(evt.outcome) if evt.outcome else {}
        except (json.JSONDecodeError, TypeError):
            pass

        if evt.event_type == "qie_cuo":
            winner = outcome.get("winner", "")
            verdict = "胜" if winner == entity.name else (
                "负" if winner else "平"
            )
            summary = outcome.get("analysis", "")[:200]
            label = f"切磋（{verdict}）"
        else:
            insights = outcome
            if isinstance(insights, dict):
                # Pick the entity's own insight if available
                summary = (
                    insights.get(entity.name)
                    or insights.get("整体感悟")
                    or next(iter(insights.values()), "")
                )
                if isinstance(summary, str):
                    summary = summary[:200]
                else:
                    summary = ""
            label = "论道"

        enriched.append({
            "label": label,
            "topic": evt.topic or "未知话题",
            "opponent": opp_name,
            "summary": summary,
        })

    # Fusion delta from log
    fusion_delta = 0.0
    if latest_log and latest_log.fusion_delta:
        try:
            fusion_delta = json.loads(latest_log.fusion_delta).get(
                "total_delta", 0.0
            )
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "player_name": player.display_name or player.username,
        "entity": entity,
        "log": latest_log,
        "day": target_day,
        "social_events": enriched,
        "fusion_delta": fusion_delta,
    }


def _build_html(data: dict) -> tuple[str, str]:
    """Build (subject, html_body) for the daily report email."""
    entity = data["entity"]
    log = data["log"]
    day = data["day"]
    delta = data["fusion_delta"]
    delta_str = f"{delta:+.4f}" if delta else "0.0000"
    delta_color = "#00ff41" if delta > 0 else (
        "#ff5555" if delta < 0 else "#888888"
    )

    subject = (
        f"【AI.me】{entity.name} · 第 {day} 天修炼报告"
        f"（聚变度 {entity.fusion_total:.3f}）"
    )

    # Fusion bars
    def bar(value: float, label: str) -> str:
        pct = max(0, min(100, int(value * 100)))
        return (
            f'<tr>'
            f'<td style="padding:4px 12px 4px 0;color:#888;width:90px;">{label}</td>'
            f'<td style="padding:4px 0;width:50px;color:#00e5ff;'
            f'font-family:monospace;">{value:.3f}</td>'
            f'<td style="padding:4px 0;">'
            f'<div style="background:#222;border-radius:3px;height:8px;'
            f'width:200px;overflow:hidden;">'
            f'<div style="background:linear-gradient(90deg,#00e5ff,#00ff41);'
            f'height:100%;width:{pct}%;"></div></div></td></tr>'
        )

    fusion_table = (
        '<table cellspacing="0" cellpadding="0" style="margin:8px 0;">'
        + bar(entity.fusion_alignment, "认知对齐")
        + bar(entity.fusion_depth, "认知深度")
        + bar(entity.fusion_coherence, "知行一致")
        + bar(entity.fusion_integrity, "自洽度")
        + "</table>"
    )

    # Social events
    social_html = ""
    if data["social_events"]:
        items = []
        for evt in data["social_events"]:
            summary_html = (
                f'<div style="color:#aaa;margin-top:4px;font-size:13px;">'
                f'{evt["summary"]}</div>' if evt["summary"] else ""
            )
            items.append(
                f'<li style="margin-bottom:12px;">'
                f'<span style="color:#ffd166;font-weight:600;">{evt["label"]}</span> '
                f'与 <span style="color:#00e5ff;">{evt["opponent"]}</span>'
                f' · <span style="color:#ddd;">{evt["topic"]}</span>'
                f'{summary_html}'
                f'</li>'
            )
        social_html = (
            '<h3 style="color:#00e5ff;margin-top:24px;'
            'border-bottom:1px solid #333;padding-bottom:6px;">今日社交</h3>'
            f'<ul style="padding-left:20px;color:#ccc;">{"".join(items)}</ul>'
        )
    else:
        social_html = (
            '<h3 style="color:#00e5ff;margin-top:24px;'
            'border-bottom:1px solid #333;padding-bottom:6px;">今日社交</h3>'
            '<p style="color:#666;font-style:italic;">今日无社交事件</p>'
        )

    # Log content
    log_content = log.content if log else "（暂无修炼日志）"
    log_html = log_content.replace("\n", "<br>")

    # Build full email
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;
            font-family:'PingFang SC','Microsoft YaHei',monospace,sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:24px;
              background:#111;color:#ddd;line-height:1.6;">

    <div style="border-bottom:2px solid #00e5ff;padding-bottom:12px;
                margin-bottom:20px;">
      <div style="color:#888;font-size:12px;letter-spacing:2px;">
        AI.ME · 念体修炼日报
      </div>
      <h1 style="margin:8px 0 4px;color:#00ff41;font-size:24px;">
        {entity.name} · 第 {day} 天
      </h1>
      <div style="color:#888;font-size:13px;">{now}</div>
    </div>

    <div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap;">
      <div style="flex:1;min-width:180px;background:#1a1a1a;
                  padding:12px 16px;border-left:3px solid #00e5ff;">
        <div style="color:#888;font-size:12px;">总聚变度</div>
        <div style="color:#00ff41;font-size:24px;font-weight:600;">
          {entity.fusion_total:.4f}
        </div>
        <div style="color:{delta_color};font-size:13px;margin-top:2px;">
          Δ {delta_str}
        </div>
      </div>
      <div style="flex:1;min-width:180px;background:#1a1a1a;
                  padding:12px 16px;border-left:3px solid #ffd166;">
        <div style="color:#888;font-size:12px;">魂念力</div>
        <div style="color:#ffd166;font-size:24px;font-weight:600;">
          {entity.soul_force}
        </div>
      </div>
    </div>

    <h3 style="color:#00e5ff;margin-top:24px;
               border-bottom:1px solid #333;padding-bottom:6px;">聚变度详情</h3>
    {fusion_table}

    {social_html}

    <h3 style="color:#00e5ff;margin-top:24px;
               border-bottom:1px solid #333;padding-bottom:6px;">修炼日志</h3>
    <div style="background:#1a1a1a;padding:16px;border-left:3px solid #00ff41;
                color:#ddd;font-size:14px;line-height:1.8;
                white-space:pre-wrap;">{log_html}</div>

    <div style="margin-top:32px;padding-top:16px;border-top:1px solid #333;
                color:#666;font-size:12px;text-align:center;">
      累计：{entity.total_feeds} 次投喂 · {entity.total_dialogues} 次对话<br>
      <a href="https://aime-7jk7.onrender.com" style="color:#00e5ff;">
        进入 AI.me 查看详情
      </a>
    </div>
  </div>
</body></html>"""

    plain = (
        f"AI.me · {entity.name} · 第 {day} 天修炼报告\n"
        f"聚变度：{entity.fusion_total:.4f} (Δ {delta_str})\n"
        f"魂念力：{entity.soul_force}\n\n"
        f"{log_content}\n"
    )

    return subject, html, plain


async def send_daily_reports():
    """Iterate all players with email enabled and send their daily report."""
    if not settings.daily_report_enabled or not settings.smtp_host:
        logger.info("邮件报告未启用，跳过。")
        return 0

    sent = 0
    async with async_session() as db:
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Player)
            .where(
                Player.email.isnot(None),
                Player.daily_report_enabled == True,
                Player.is_active == True,
            )
            .options(selectinload(Player.entity))
        )
        players = list(result.scalars().all())

        for player in players:
            try:
                data = await _gather_data(player, db)
                if not data:
                    continue
                subject, html, plain = _build_html(data)
                ok = await send_email(player.email, subject, html, plain)
                if ok:
                    sent += 1
            except Exception as e:
                logger.error(f"为 {player.username} 生成日报失败: {e}")

    logger.info(f"日报已发送 {sent} 封。")
    return sent
