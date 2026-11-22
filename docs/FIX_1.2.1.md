# V-FINAL 1.2.1 fixes

- Fixed MT5 tick collection in the demo runner: `copy_ticks_range` now receives native timezone-aware `datetime` objects instead of calling `to_pydatetime()` on a Python datetime.
- Fixed `python run_vfinal.py status` when `data/labels/vfinal_dataset.csv` exists but is empty; it now reports `COLLECTING` instead of raising `pandas.errors.EmptyDataError`.
- Status output includes the dataset path.
- Dashboard now shows a clear waiting state when the demo runner has not started and exposes the last update timestamp.
