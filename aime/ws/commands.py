"""MUD command parser — maps Chinese/English commands to handler names."""


COMMAND_MAP = {
    # Chinese commands
    "投喂": "feed",
    "对话": "dialogue",
    "设定方向": "set_direction",
    "查看日志": "view_log",
    "查看状态": "view_status",
    "查看天榜": "view_leaderboard",
    "论道": "lun_dao",
    "切磋": "qie_cuo",
    "帮助": "help",
    # Slash shortcuts
    "/f": "feed",
    "/t": "dialogue",
    "/s": "view_status",
    "/l": "view_log",
    "/r": "view_leaderboard",
    "/d": "set_direction",
    "/ld": "lun_dao",
    "/qc": "qie_cuo",
    "/h": "help",
    # English aliases
    "feed": "feed",
    "talk": "dialogue",
    "chat": "dialogue",
    "status": "view_status",
    "log": "view_log",
    "rank": "view_leaderboard",
    "leaderboard": "view_leaderboard",
    "direction": "set_direction",
    "debate": "lun_dao",
    "spar": "qie_cuo",
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

    return ("unknown", raw)
