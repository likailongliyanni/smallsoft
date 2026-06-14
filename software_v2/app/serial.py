import hashlib
import platform
import uuid


def _raw_machine_id() -> str:
    mac = uuid.getnode()
    node = platform.node()
    processor = platform.processor()
    system = platform.system()
    return f"{mac}-{node}-{processor}-{system}"


def get_serial() -> str:
    raw = _raw_machine_id()
    digest = hashlib.sha256(raw.encode()).hexdigest().upper()
    parts = [digest[i:i + 4] for i in range(0, 20, 4)]
    return "-".join(parts)
