import io
import unittest
from unittest.mock import patch

from rich.console import Console

from bili2music.config import Config
from bili2music.core.dialogue import _merge, collect_intent, rule_parse
from bili2music.llm import LLMClient
from bili2music.models import Intent


class StubLLM:
    """LLM that asks one soft clarification and adds no slots."""
    def __init__(self):
        self.calls = 0

    def chat_json(self, *a, **kw):
        self.calls += 1
        return {"slots": {}, "need_more_info": True, "reply": "想找周杰伦相关内容",
                "questions": [{"key": "keyword_detail", "text": "偏好哪种风格？",
                               "choices": ["现场", "录音室"]}]}


class TestRuleParse(unittest.TestCase):
    def test_favorite_both(self):
        it = rule_parse("把收藏夹 https://space.bilibili.com/123/favlist?fid=123456 里的视频音频都下了")
        self.assertEqual(it.task, "favorite")
        self.assertEqual(it.favorite_id, "123456")
        self.assertEqual(it.mode, "both")
        self.assertEqual(it.keyword, "")

    def test_search_site_audio(self):
        it = rule_parse("搜「周杰伦 现场」，全站找，挑 10 个下成 mp3")
        self.assertEqual(it.task, "search")
        self.assertEqual(it.keyword, "周杰伦 现场")
        self.assertEqual(it.scope, "site")
        self.assertEqual(it.mode, "audio")
        self.assertEqual(it.limit, 10)

    def test_folder_search(self):
        it = rule_parse("在我的收藏夹里找 坂本龙一")
        self.assertEqual(it.task, "folder_search")
        self.assertEqual(it.keyword, "坂本龙一")
        self.assertEqual(it.scope, "folder")

    def test_list_folders(self):
        self.assertEqual(rule_parse("列出我的收藏夹").task, "folders")

    def test_no_guess(self):
        it = rule_parse("下载")
        self.assertIn(it.task, ("", "favorite"))
        self.assertEqual(it.mode, "")


class TestMissingSlots(unittest.TestCase):
    def test_favorite_needs_mode(self):
        it = Intent(task="favorite", favorite_id="123")
        self.assertEqual(it.missing(), ["mode"])

    def test_search_all_missing(self):
        self.assertEqual(set(Intent(task="search").missing()),
                         {"keyword", "scope", "mode"})

    def test_search_folder_needs_fid(self):
        it = Intent(task="search", keyword="lofi", scope="folder", mode="audio")
        self.assertEqual(it.missing(), ["favorite_id"])

    def test_ready(self):
        it = Intent(task="favorite", favorite_id="123", mode="audio")
        self.assertEqual(it.missing(), [])


class TestMerge(unittest.TestCase):
    def test_reject_invalid_enums_and_keep_valid(self):
        it = Intent()
        _merge(it, {"task": "favorite", "mode": " hologram ", "scope": "site",
                    "favorite_id": "fid=889", "limit": "12"})
        self.assertEqual(it.task, "favorite")
        self.assertEqual(it.mode, "")
        self.assertEqual(it.scope, "site")
        self.assertEqual(it.favorite_id, "889")
        self.assertEqual(it.limit, 12)


class TestCollectIntent(unittest.TestCase):
    def setUp(self):
        self.console = Console(file=io.StringIO(), quiet=True)

    def test_asks_for_missing_mode(self):
        cfg = Config(llm_api_key="")             # LLM disabled -> rule-based questions
        with patch.object(Console, "input", return_value="1"):
            it = collect_intent(LLMClient(cfg), cfg, "下载收藏夹 https://space.bilibili.com/1/favlist?fid=123456 的内容",
                                None, self.console)
        self.assertEqual(it.task, "favorite")
        self.assertEqual(it.favorite_id, "123456")
        self.assertEqual(it.mode, "audio")
        self.assertEqual(it.missing(), [])

    def test_non_interactive_never_asks(self):
        cfg = Config(llm_api_key="")
        with patch.object(Console, "input", side_effect=AssertionError("should not ask")):
            it = collect_intent(LLMClient(cfg), cfg, "下载收藏夹 https://space.bilibili.com/1/favlist?fid=123456 的内容",
                                None, self.console, non_interactive=True)
        self.assertEqual(it.mode, "audio")       # documented default
        self.assertEqual(it.missing(), [])

    def test_llm_soft_clarification_plus_required_slots(self):
        cfg = Config(llm_api_key="x")
        llm = StubLLM()
        answers = iter(["现场版", "1", "2"])     # clarification, scope, mode
        with patch.object(Console, "input", side_effect=lambda *a, **k: next(answers)):
            it = collect_intent(llm, cfg, "搜「周杰伦」", None, self.console)
        self.assertEqual(it.task, "search")
        self.assertEqual(it.keyword, "周杰伦")
        self.assertIn("现场版", " ".join(it.notes))
        self.assertEqual(it.scope, "site")
        self.assertEqual(it.mode, "video")
        self.assertEqual(it.missing(), [])


if __name__ == "__main__":
    unittest.main()
