"""Styled text output for the MUD terminal."""

import json


def render(msg_type: str, content: str, **kwargs) -> str:
    """Render a message as JSON for the WebSocket client."""
    return json.dumps({
        "type": msg_type,
        "content": content,
        **kwargs,
    }, ensure_ascii=False)


def system_msg(content: str) -> str:
    return render("system", content)


def narrative(content: str) -> str:
    return render("narrative", content)


def entity_speech(content: str, streaming: bool = False, done: bool = False) -> str:
    return render("entity_speech", content, streaming=streaming, done=done)


def error_msg(content: str) -> str:
    return render("error", content)


def highlight(content: str) -> str:
    return render("highlight", content)


def divider() -> str:
    return render("divider", "━" * 50)


def render_status(entity_data: dict) -> str:
    """Render entity status in MUD format."""
    fusion = entity_data.get("fusion", {})
    social = entity_data.get("social", {})
    lines = [
        "━━━ 念体状态 ━━━",
        "",
        f"  名号：{entity_data['name']}",
        f"  修炼天数：第 {entity_data['cultivation_day']} 天",
        "",
        f"  本心：「{entity_data['core_belief'][:80]}{'...' if len(entity_data['core_belief']) > 80 else ''}」",
        "",
        f"  修炼方向：{entity_data.get('current_direction') or '自由探索'}",
        "",
        f"  聚变度：{fusion.get('total', 0):.3f}",
        f"    ├ 认知对齐：{fusion.get('alignment', 0):.3f}  {_bar(fusion.get('alignment', 0))}",
        f"    ├ 认知深度：{fusion.get('depth', 0):.3f}  {_bar(fusion.get('depth', 0))}",
        f"    ├ 知行一致：{fusion.get('coherence', 0):.3f}  {_bar(fusion.get('coherence', 0))}",
        f"    └ 自洽度：  {fusion.get('integrity', 0):.3f}  {_bar(fusion.get('integrity', 0))}",
        "",
        f"  魂念力：{entity_data.get('soul_force', 10)}",
        "",
        "━━━ 活动记录 ━━━",
        "",
        f"  总投喂：{entity_data.get('total_feeds', 0)} 次",
        f"  总对话：{entity_data.get('total_dialogues', 0)} 次",
        f"  论道：  {social.get('lun_dao_count', 0)} 次",
        f"  切磋：  {social.get('qie_cuo_count', 0)} 次"
        + (f"  （{social.get('wins', 0)}胜 {social.get('losses', 0)}负）"
           if social.get('qie_cuo_count', 0) > 0 else ""),
    ]

    recent = social.get("recent", [])
    if recent:
        lines.append("")
        lines.append("  近期社交：")
        for evt in recent:
            lines.append(f"    · {evt}")

    lines.append("")
    lines.append("━" * 30)
    return "\n".join(lines)


def render_leaderboard(entries: list[dict]) -> str:
    """Render the 天榜 leaderboard."""
    lines = [
        "━━━ 天 榜 ━━━",
        "",
        "  #   念体        修炼方向          聚变度   魂念力",
    ]
    for i, e in enumerate(entries, 1):
        name = e["name"].ljust(10)
        direction = (e.get("current_direction") or "自由探索")[:12].ljust(14)
        fusion = f"{e['fusion_total']:.3f}"
        soul = str(e["soul_force"]).rjust(8)
        marker = "  ◀ 你" if e.get("is_self") else ""
        lines.append(f"  {i:<4}{name}{direction}{fusion}{soul}{marker}")
    lines.append("")
    lines.append("━" * 50)
    return "\n".join(lines)


def render_help() -> str:
    """Render help text."""
    return """━━━ 命令列表 ━━━

  投喂          /f           向念体投喂知识（//end 结束）
  对话 <内容>   /t <msg>     与你的念体对话
  查看状态      /s           查看念体状态和聚变度
  查看日志 [天] /l [day]     查看修炼日志
  查看天榜      /r           查看聚变度排行榜
  设定方向 <向> /d <dir>     设定修炼方向
  论道          /ld          触发论道事件
  切磋          /qc          触发切磋事件
  帮助          /h           显示此帮助信息

━━━━━━━━━━━━━━━━━━━━━━"""


def _bar(value: float, width: int = 15) -> str:
    """Render a progress bar."""
    filled = int(value * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"
