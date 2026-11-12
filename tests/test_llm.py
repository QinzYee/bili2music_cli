import unittest
from unittest.mock import patch

from bili2music.config import Config
from bili2music.llm.client import LLMClient, LLMError, _loads_json


class TestJsonParsing(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(_loads_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        self.assertEqual(_loads_json('```json\n{"a": 2}\n```'), {"a": 2})

    def test_surrounded_by_text(self):
        self.assertEqual(_loads_json('好的，结果如下：\n{"a": 3, "b": [1,2]}\n希望有帮助'),
                         {"a": 3, "b": [1, 2]})

    def test_invalid(self):
        with self.assertRaises(ValueError):
            _loads_json("完全没有 JSON")


class TestChatJson(unittest.TestCase):
    def test_retries_with_stricter_prompt(self):
        client = LLMClient(Config(llm_api_key="x"))
        with patch.object(LLMClient, "chat", side_effect=["抱歉我说错了", '{"task":"favorite"}']) as m:
            out = client.chat_json("system", "user")
        self.assertEqual(out, {"task": "favorite"})
        self.assertEqual(m.call_count, 2)
        self.assertIn("只输出一个 JSON", m.call_args.args[1])

    def test_gives_up_cleanly(self):
        client = LLMClient(Config(llm_api_key="x"))
        with patch.object(LLMClient, "chat", return_value="nope"):
            with self.assertRaises(LLMError):
                client.chat_json("system", "user")


if __name__ == "__main__":
    unittest.main()
