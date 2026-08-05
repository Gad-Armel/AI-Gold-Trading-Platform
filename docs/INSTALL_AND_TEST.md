# Install and Test V6.2

```text
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" -m pip install -r ".\requirements.txt"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_scalping_all_tests.py"
& "C:\Users\Gad Asopjio\AppData\Local\Microsoft\WindowsApps\python3.11.exe" ".\run_scalping_audit.py"
```

Expected final validation:

```text
Validation scripts failed: 0/8
All V6 validation scripts passed.
Audit Status: PASSED
```

Start shadow calibration:

```text
& "...\python3.11.exe" ".\run_scalping_shadow_loop.py" --max-minutes 0
```
