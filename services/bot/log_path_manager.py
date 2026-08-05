from pathlib import Path
from datetime import datetime

from config.settings import LOG_FILE_PATH, SIGNAL_LOG_FOLDER


def get_log_date_folder_name():
    try:
        from config.settings import LOG_DATE_FORMAT
    except ImportError:
        LOG_DATE_FORMAT = "%Y-%m-%d"

    return datetime.now().strftime(LOG_DATE_FORMAT)


def use_daily_log_folders():
    try:
        from config.settings import USE_DAILY_LOG_FOLDERS
        return USE_DAILY_LOG_FOLDERS
    except ImportError:
        return True


def get_logs_root_folder():
    return Path(LOG_FILE_PATH).parent


def get_daily_log_folder():
    logs_root = get_logs_root_folder()

    if use_daily_log_folders():
        return logs_root / get_log_date_folder_name()

    return logs_root


def get_daily_cycle_log_path():
    daily_folder = get_daily_log_folder()
    daily_folder.mkdir(parents=True, exist_ok=True)

    log_filename = Path(LOG_FILE_PATH).name
    return daily_folder / log_filename


def get_daily_signal_log_folder():
    if use_daily_log_folders():
        daily_folder = get_daily_log_folder()
        signal_folder_name = Path(SIGNAL_LOG_FOLDER).name
        final_folder = daily_folder / signal_folder_name
    else:
        final_folder = Path(SIGNAL_LOG_FOLDER)

    final_folder.mkdir(parents=True, exist_ok=True)
    return final_folder


def ensure_daily_log_structure():
    get_daily_log_folder().mkdir(parents=True, exist_ok=True)
    get_daily_signal_log_folder().mkdir(parents=True, exist_ok=True)