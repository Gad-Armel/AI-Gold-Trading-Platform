from __future__ import annotations

import os

from config import settings


def get_emergency_stop_file_path() -> str:
    return str(getattr(settings, "EMERGENCY_STOP_FILE", "data/EMERGENCY_STOP.flag"))


def is_emergency_stop_enabled() -> bool:
    if bool(getattr(settings, "EMERGENCY_STOP", False)):
        return True
    return os.path.exists(get_emergency_stop_file_path())


def check_emergency_stop() -> tuple[bool, str]:
    if bool(getattr(settings, "EMERGENCY_STOP", False)):
        return True, "Emergency stop is enabled in config.settings. Bot cycle blocked."

    path = get_emergency_stop_file_path()
    if os.path.exists(path):
        reason = ""
        try:
            with open(path, "r", encoding="utf-8") as file:
                reason = file.read().strip()
        except OSError:
            pass
        message = f"Runtime emergency-stop file is active: {path}."
        if reason:
            message += f" Reason: {reason}"
        return True, message

    return False, "Emergency stop is not enabled."
