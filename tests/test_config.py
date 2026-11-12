import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bili2music import config as cfgmod
from bili2music.config import Config


class TestConfig(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, value in (("APP_DIR", root), ("CONFIG_PATH", root / "config.toml"),
                            ("COOKIE_PATH", root / "cookies.txt")):
            p = patch.object(cfgmod, name, value)
            p.start()
            self.addCleanup(p.stop)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_roundtrip(self):
        cfg = Config(llm_model="gpt-4o-mini", llm_api_key="sk-test",
                     audio_format="m4a", max_results=7, overwrite=True)
        path = cfgmod.save_config(cfg)
        self.assertTrue(path.is_file())
        loaded = cfgmod.load_config()
        self.assertEqual(loaded.llm_model, "gpt-4o-mini")
        self.assertEqual(loaded.llm_api_key, "sk-test")
        self.assertEqual(loaded.audio_format, "m4a")
        self.assertEqual(loaded.max_results, 7)
        self.assertTrue(loaded.overwrite)

    def test_env_override(self):
        cfgmod.save_config(Config(llm_model="from-file"))
        with patch.dict(os.environ, {"B2M_LLM_MODEL": "from-env"}):
            self.assertEqual(cfgmod.load_config().llm_model, "from-env")

    def test_common_key_alias(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-alias"}):
            self.assertEqual(cfgmod.load_config().llm_api_key, "sk-alias")

    def test_llm_ready(self):
        self.assertFalse(Config().llm_ready())
        self.assertTrue(Config(llm_api_key="x").llm_ready())
        self.assertTrue(Config(llm_provider="ollama").llm_ready())

    def test_cookie_file(self):
        cfg = Config(sessdata="abc,123", dede_user_id="42")
        path = cfgmod.write_cookie_file(cfg)
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("SESSDATA\tabc,123", text)
        self.assertIn("DedeUserID\t42", text)
        self.assertIsNone(cfgmod.write_cookie_file(Config()))

    def test_output_path(self):
        with patch("pathlib.Path.home", return_value=Path("C:/Users/someone")):
            self.assertEqual(Config().output_path.name, "bili2music")
        self.assertEqual(Config(output_dir="D:/music").output_path, Path("D:/music"))


if __name__ == "__main__":
    unittest.main()
