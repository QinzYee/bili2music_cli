"""LLM backends: OpenAI-compatible HTTP API and local Ollama."""
from __future__ import annotations

import json
import re

import httpx

from ..config import Config


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    @property
    def provider(self) -> str:
        return (self.cfg.llm_provider or "openai").lower()

    def chat(self, system: str, user: str, *, temperature: float = 0.2,
             timeout: int | None = None) -> str:
        timeout = timeout or self.cfg.llm_timeout
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        if self.provider == "ollama":
            return self._ollama(messages, temperature, timeout)
        return self._openai(messages, temperature, timeout)

    def _openai(self, messages, temperature: float, timeout: int) -> str:
        url = self.cfg.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.cfg.llm_api_key}",
                   "Content-Type": "application/json"}
        body = {"model": self.cfg.llm_model, "messages": messages,
                "temperature": temperature, "stream": False}
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接大模型服务 {url}：{exc}") from exc
        if r.status_code == 401:
            raise LLMError("API Key 无效或未授权（401），请用 `b2m config` 检查")
        if r.status_code == 429:
            raise LLMError("大模型接口限流（429），请稍后重试或换一家服务商")
        if r.status_code >= 400:
            raise LLMError(f"大模型接口返回 {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"大模型返回格式异常：{r.text[:200]}") from exc

    def _ollama(self, messages, temperature: float, timeout: int) -> str:
        url = self.cfg.ollama_base_url.rstrip("/") + "/api/chat"
        body = {"model": self.cfg.ollama_model, "messages": messages,
                "stream": False, "format": "json",
                "options": {"temperature": temperature}}
        try:
            r = httpx.post(url, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"无法连接 Ollama {url}（是否已运行 `ollama serve`？）：{exc}") from exc
        if r.status_code >= 400:
            raise LLMError(f"Ollama 返回 {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["message"]["content"] or ""
        except (KeyError, ValueError) as exc:
            raise LLMError(f"Ollama 返回格式异常：{r.text[:200]}") from exc

    def chat_json(self, system: str, user: str, *, temperature: float = 0.2) -> dict:
        """Ask for JSON, retry once with a stricter instruction, parse leniently."""
        last_error = ""
        for attempt in range(2):
            prompt = user if attempt == 0 else (
                user + "\n\n【重要】上一次输出无法解析为 JSON。只输出一个 JSON 对象，"
                       "不要 Markdown 代码块、不要任何解释文字。")
            try:
                text = self.chat(system + "\n只输出 JSON 对象，不要任何解释或 Markdown。",
                                 prompt, temperature=temperature)
                parsed = _loads_json(text)
                if isinstance(parsed, dict):
                    return parsed
                last_error = "返回不是 JSON 对象"
            except LLMError as exc:
                raise
            except Exception as exc:
                last_error = str(exc)
        raise LLMError(f"大模型未返回可解析的 JSON：{last_error}")

    def ping(self) -> tuple[bool, str]:
        """Cheap connectivity/config check."""
        try:
            out = self.chat("你是一个测试助手。", "回复ok两个字母即可。", temperature=0, timeout=15)
            return True, (out or "").strip()[:40]
        except LLMError as exc:
            return False, str(exc)


def _loads_json(text: str) -> dict:
    text = (text or "").strip()
    # Strip markdown fences.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("没有找到 JSON 对象")
