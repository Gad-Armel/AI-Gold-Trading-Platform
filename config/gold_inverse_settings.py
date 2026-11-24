"""Separate inverse demo executor; never used by Advisor1."""
SYMBOL = 'XAUUSD'
SOURCE_MAGIC = 631011
MAGIC = 631021
LOT = .01
MAX_INVERSE_POSITIONS = 2
PAIRING_ENABLED = False
EXECUTOR_ENABLED = False
MAX_COMBINED_POSITIONS = 4
MAX_PLANNED_RISK_USD = 5.
MAX_ENTRY_DELAY_SECONDS = 5.
CONFIRMATION = 'I_ACCEPT_INVERSE_DEMO_RISK'
STATE_PATH = 'data/runtime/gold_inverse_state.json'
STATUS_PATH = 'data/runtime/gold_inverse_status.json'
STOP_PATH = 'data/runtime/stop_gold_inverse.flag'
JOURNAL_PATH = 'data/demo/gold_inverse_journal.jsonl'
