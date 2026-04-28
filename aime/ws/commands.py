"""MUD command parser — maps Chinese/English commands to handler names."""


COMMAND_MAP = {
    # Chinese commands
    "投喂": "feed",
    "对话": "dialogue",
    "设定方向": "set_direction",
    "查看日志": "view_log",
    "查看状态": "view_status",
    "查看天榜": "view_leaderboard",
    "查看进度": "view_progress",
    "进度": "view_progress",
    "今日": "view_progress",
    "论道": "lun_dao",
    "切磋": "qie_cuo",
    "设置邮箱": "set_email",
    "邮箱": "set_email",
    "帮助": "help",
    # Slash shortcuts
    "/f": "feed",
    "/t": "dialogue",
    "/s": "view_status",
    "/l": "view_log",
    "/r": "view_leaderboard",
    "/p": "view_progress",
    "/d": "set_direction",
    "/ld": "lun_dao",
    "/qc": "qie_cuo",
    "/email": "set_email",
    "/h": "help",
    # English aliases
    "feed": "feed",
    "talk": "dialogue",
    "chat": "dialogue",
    "status": "view_status",
    "log": "view_log",
    "rank": "view_leaderboard",
    "leaderboard": "view_leaderboard",
    "progress": "view_progress",
    "today": "view_progress",
    "direction": "set_direction",
    "debate": "lun_dao",
    "spar": "qie_cuo",
    "email": "set_email",
    "help": "help",
}


def parse_command(raw: str) -> tuple[str, str]:
    """Parse raw input into (handler_name, args).

    Returns ("unknown", raw) if command not recognized.
    """
    raw = raw.strip()
    if not raw:
        return ("empty", "")

    # Try matching longest prefix first
    for cmd in sorted(COMMAND_MAP.keys(), key=len, reverse=True):
        if raw == cmd or raw.startswith(cmd + " "):
            args = raw[len(cmd):].strip()
            return (COMMAND_MAP[cmd], args)

    # Default: non-slash input treated as dialogue
    if not raw.startswith("/"):
        return ("dialogue", raw)

    return ("unknown", raw)
