from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from tools import launch_gold_demo


class BackgroundDemoLaunchTests(unittest.TestCase):
    def test_background_command_uses_the_guarded_demo_entrypoint(self) -> None:
        command = launch_gold_demo.demo_bot_command("python.exe", "DEMO_TOKEN")

        self.assertEqual(command[0], "python.exe")
        self.assertIn(str(launch_gold_demo.ROOT / "run_gold_ai.py"), command)
        self.assertEqual(command[command.index("--mode") + 1], "demo")
        self.assertEqual(command[command.index("--confirm") + 1], "DEMO_TOKEN")
        self.assertIn("--no-dashboard", command)

    def test_live_status_requires_running_and_a_fresh_timestamp(self) -> None:
        now = datetime.now(timezone.utc).timestamp()
        fresh = {
            "status": "RUNNING",
            "updated_at": datetime.fromtimestamp(now - 2, timezone.utc).isoformat(),
        }
        stopped = dict(fresh, status="STOPPED")
        stale = dict(
            fresh,
            updated_at=datetime.fromtimestamp(now - 120, timezone.utc).isoformat(),
        )

        self.assertTrue(launch_gold_demo.status_is_live(fresh, now=now))
        self.assertFalse(launch_gold_demo.status_is_live(stopped, now=now))
        self.assertFalse(launch_gold_demo.status_is_live(stale, now=now))

    def test_background_launch_is_independent_and_waits_for_heartbeat(self) -> None:
        fake_process = Mock(pid=9123)
        fake_process.poll.return_value = None
        live = {
            "status": "RUNNING",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            launch_gold_demo.subprocess, "Popen", return_value=fake_process
        ) as popen, patch.object(
            launch_gold_demo, "read_consensus_status", side_effect=[None, live]
        ), patch.object(launch_gold_demo.time, "sleep"):
            runtime = Path(directory)
            pid = launch_gold_demo.start_demo_bot_background(
                "python.exe", "DEMO_TOKEN", runtime_directory=runtime, timeout=1
            )

            self.assertEqual(
                json.loads((runtime / "aigold-demo.pid.json").read_text())["pid"],
                9123,
            )

        self.assertEqual(pid, 9123)
        call = popen.call_args
        self.assertEqual(call.args[0], launch_gold_demo.demo_bot_command("python.exe", "DEMO_TOKEN"))
        self.assertIs(call.kwargs["stdin"], launch_gold_demo.subprocess.DEVNULL)
        self.assertTrue(call.kwargs["creationflags"])


if __name__ == "__main__":
    unittest.main()
