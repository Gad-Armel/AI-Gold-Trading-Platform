"""
Asynchronous Atomic File Bridge for MetaTrader 5 Expert Advisor (MQL5).
Writes structured Market Intelligence payloads via temporary file replacement,
preventing race conditions or partial file reads in MT5.
"""

from typing import Dict, Any, Optional
import os
import json
import tempfile
import logging

logger = logging.getLogger("XAUUSD_FileBridge")


class MT5FileBridge:
    """
    Communicates with MT5 Expert Advisor by publishing an atomic JSON file.
    
    HOW IT WORKS:
    1. Writes JSON to a temporary file in the destination folder.
    2. Atomically replaces destination file (e.g. `xauusd_ai_signals.json`).
    3. The MT5 EA opens `xauusd_ai_signals.json` using MQL5 `FileOpen(..., FILE_READ|FILE_BIN|FILE_SHARE_READ)`
       and parses the advisory signals with zero locking contention.
    """

    def __init__(self, target_filepath: str = "MQL5/Files/xauusd_ai_signals.json"):
        self.target_filepath = target_filepath
        # Ensure parent directory exists
        parent_dir = os.path.dirname(os.path.abspath(target_filepath))
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                logger.warning("Could not create bridge directory %s: %s", parent_dir, e)

    def publish_intelligence(self, payload: Dict[str, Any]) -> bool:
        """
        Atomically writes the Market Intelligence payload to the bridge file.
        Returns True on success, False on error.
        """
        # Enforce non-execution guarantee inside the payload itself
        payload["ea_override_permitted"] = False
        payload["execution_authority"] = "MT5_EA_RISK_MANAGER"
        payload["disclaimer"] = (
            "Quantitative Market Intelligence advisory output only. "
            "MT5 EA RiskManager has absolute priority and must approve all trade placement and sizing."
        )

        target_dir = os.path.dirname(os.path.abspath(self.target_filepath))
        if not os.path.exists(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception:
                pass

        try:
            # 1. Write to temporary file in the same filesystem directory to guarantee atomic rename
            with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
                json.dump(payload, tf, indent=2)
                temp_name = tf.name

            # 2. Atomic rename/replace (atomic on POSIX and modern Windows NTFS)
            os.replace(temp_name, self.target_filepath)
            return True

        except Exception as e:
            logger.error("Failed to write intelligence payload to file bridge: %s", e)
            return False

    def read_latest(self) -> Optional[Dict[str, Any]]:
        """Reads the currently published payload from disk (used for verification/testing)."""
        if not os.path.exists(self.target_filepath):
            return None
        try:
            with open(self.target_filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read latest bridge file: %s", e)
            return None
