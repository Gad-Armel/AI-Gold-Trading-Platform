from datetime import datetime

from services.bot.log_path_manager import get_daily_signal_log_folder


def _safe_symbol(symbol):
    return str(symbol).replace("/", "_").replace("\\", "_").replace(":", "_")


def save_signal_text_log(symbol, signal_text):
    signal_folder = get_daily_signal_log_folder()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"signal_{_safe_symbol(symbol)}_{timestamp}.txt"

    file_path = signal_folder / filename

    with open(file_path, "w", encoding="utf-8") as file:
        file.write(signal_text)

    print(f"Signal text saved to: {file_path}")

    return str(file_path)


# Compatibility aliases
def log_signal_text(symbol, signal_text):
    return save_signal_text_log(symbol, signal_text)


def save_signal_text(symbol, signal_text):
    return save_signal_text_log(symbol, signal_text)