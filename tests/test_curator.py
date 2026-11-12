import io
import json
import tempfile
import unittest
from pathlib import Path

from rich.console import Console

from bili2music.config import Config
from bili2music.core.curator import build_full_plan, curate, default_filename
from bili2music.core.planner import save_plan
from bili2music.models import Intent, PlanItem, VideoItem


def mk(bvid, title, owner="UP", play=100):
    return VideoItem(bvid=bvid, title=title, owner=owner,
                     duration=210, play=play, source="search")


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, *a, **kw):
        return self.payload


class TestFullPlan(unittest.TestCase):
    def test_all_items_and_dedupe(self):
        items = [mk("BV1aa", "A"), mk("BV1bb", "B"), mk("BV1aa", "A dup")]
        plan = build_full_plan(items)
        self.assertEqual(len(plan), 2)
        self.assertTrue(all(p.reason for p in plan))
        self.assertEqual(plan[0].filename, default_filename(items[0]))

    def test_filename_safe(self):
        name = default_filename(mk("BV1aa", '标题: A/B*C?', "UP|主"))
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, name)


class TestCurate(unittest.TestCase):
    def setUp(self):
        self.console = Console(file=io.StringIO(), quiet=True)
        self.items = [mk("BV0000000001", "周杰伦 现场 晴天"),
                      mk("BV0000000002", "周杰伦 录音室 专辑"),
                      mk("BV0000000003", "完全无关的做饭视频", play=1),
                      mk("BV0000000004", "周杰伦 现场 七里香"),
                      mk("BV0000000005", "另一个无关视频", play=2)]
        self.intent = Intent(task="search", keyword="周杰伦 现场",
                             scope="site", mode="audio", limit=3)

    def test_fallback_without_llm(self):
        plan = curate(None, Config(), self.intent, self.items, self.console)
        self.assertTrue(0 < len(plan) <= 3)
        self.assertTrue(all(p.video.bvid in {v.bvid for v in self.items} for p in plan))
        self.assertIn("未经大模型整理", plan[0].reason)

    def test_llm_selection(self):
        llm = FakeLLM({"summary": "挑现场版", "items": [
            {"bvid": "BV0000000004", "score": 95, "reason": "现场版音质好",
             "filename": "周杰伦 - 七里香 现场"},
            {"bvid": "BV0000000001", "score": 90, "reason": "现场版",
             "filename": "周杰伦 - 晴天 现场"},
        ]})
        plan = curate(llm, Config(llm_api_key="x"), self.intent, self.items, self.console)
        self.assertEqual([p.video.bvid for p in plan], ["BV0000000004", "BV0000000001"])
        self.assertEqual(plan[0].reason, "现场版音质好")

    def test_hallucinated_bvids_are_rejected(self):
        llm = FakeLLM({"items": [
            {"bvid": "BVFAKEFAKE01", "score": 99, "reason": "编的", "filename": "x"},
            {"bvid": "BV0000000001", "score": 50, "reason": "真的", "filename": "y"},
        ]})
        plan = curate(llm, Config(llm_api_key="x"), self.intent, self.items, self.console)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].video.bvid, "BV0000000001")

    def test_all_hallucinated_falls_back(self):
        llm = FakeLLM({"items": [{"bvid": "BVFAKEFAKE01", "score": 99, "filename": "x"}]})
        plan = curate(llm, Config(llm_api_key="x"), self.intent, self.items, self.console)
        self.assertTrue(plan)
        self.assertTrue(all(p.video.bvid in {v.bvid for v in self.items} for p in plan))


class TestPlanPersistence(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            plan = [PlanItem(video=mk("BV0000000001", "歌"), filename="UP - 歌",
                             reason="测试", score=88)]
            intent = Intent(task="favorite", favorite_id="999", mode="audio")
            path = save_plan(plan, intent, root)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["mode"], "audio")
            back = PlanItem.from_dict(data["items"][0])
            self.assertEqual(back.video.bvid, "BV0000000001")
            self.assertEqual(back.filename, "UP - 歌")


if __name__ == "__main__":
    unittest.main()
