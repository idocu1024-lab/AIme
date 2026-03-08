import uuid


def gen_short_id() -> str:
    return uuid.uuid4().hex[:12]
