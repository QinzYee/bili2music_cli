import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from bili2music.cli import App, build_parser, main
from bili2music.models import PlanItem, VideoItem


class TestParser(unittest.TestCase):
    def test_agent_flags(self):
        a = build_parser().parse_args(
            ["search", "周杰伦", "--scope", "site", "--mode", "audio",
             "--limit", "3", "--dry-run", "--yes", "--json"])
        self.assertTrue(a.json and a.yes and a.dry_run)
        self.assertEqual(a.keyword, ["周杰伦"])
        self.assertEqual(a.limit, 3)

    def test_plan_command(self):
        a = build_parser().parse_args(["plan", "x.json", "--mode", "video", "--json"])
        self.assertEqual(a.cmd, "plan")
        self.assertEqual(a.path, "x.json")
        self.assertEqual(a.mode, "video")

    def test_search_fav_flag(self):
        a = build_parser().parse_args(["search", "lofi", "--scope", "folder", "--fav", "12345"])
        self.assertEqual(a.fav, "12345")


class TestBriefPlan(unittest.TestCase):
    def test_schema(self):
        plan = [PlanItem(video=VideoItem(bvid="BV1aa0000001", title="歌", owner="UP", duration=200),
                         filename="UP - 歌", reason="理由", score=90)]
        brief = App._brief_plan(plan)
        self.assertEqual(list(brief[0].keys()),
                         ["bvid", "title", "up", "duration", "filename", "reason", "score"])
        self.assertEqual(brief[0]["bvid"], "BV1aa0000001")


class TestMainJson(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(argv)
        return rc, json.loads(buf.getvalue())

    def test_no_subcommand_is_explicit_error(self):
        rc, out = self._run(["--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "error")
        self.assertIn("error", out)

    def test_login_is_blocked_in_json_mode(self):
        rc, out = self._run(["login", "--json"])
        self.assertEqual(rc, 1)
        self.assertIn("登录", out["error"])

    def test_plan_dry_run_returns_clean_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "plan.json"
            payload = {
                "task": "search", "keyword": "lofi", "mode": "audio",
                "output_dir": d, "count": 1,
                "items": [{"video": VideoItem(bvid="BV1aa0000001", title="歌",
                                              owner="UP").to_dict(),
                           "filename": "UP - 歌", "reason": "测试", "score": 90}],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            rc, out = self._run(["plan", str(path), "--dry-run", "--yes", "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "plan_only")
            self.assertEqual(out["source"], "plan.json")
            self.assertEqual(out["plan_count"], 1)
            self.assertEqual(out["plan"][0]["bvid"], "BV1aa0000001")
            self.assertEqual(out["downloaded"], 0)
            self.assertEqual(out["exit_code"], 0)

    def test_missing_plan_file(self):
        rc, out = self._run(["plan", "definitely-missing-plan.json", "--json"])
        self.assertEqual(rc, 1)
        self.assertEqual(out["status"], "error")


if __name__ == "__main__":
    unittest.main()
