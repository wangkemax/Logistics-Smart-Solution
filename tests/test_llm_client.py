"""MiniMax credentials stay on the MiniMax host."""
import urllib.error
import urllib.request

from backend.services.assumption_validation import acceptable_assumption_value
from backend.services.llm_client import complete_text


def test_minimax_key_is_not_sent_to_openai(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "mm-secret-not-openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        raise urllib.error.URLError("stopped")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert complete_text("hello", max_retries=1) is None
    assert "api.openai.com" not in captured["url"]
    assert "minimaxi.com" in captured["url"]
    assert "mm-secret-not-openai" in captured["auth"]


def test_openai_key_used_only_when_it_is_separate(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-separate-openai")
    captured = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        raise urllib.error.URLError("stopped")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    complete_text("hello", max_retries=1)
    assert captured["url"].startswith("https://api.openai.com/")


def test_numeric_assumption_ranges():
    assert acceptable_assumption_value("sku_count", 8000)
    assert not acceptable_assumption_value("sku_count", 9_000_000_000)
    assert not acceptable_assumption_value("warehouse_area", 1)
    assert acceptable_assumption_value("project_name", "澄海汽车贸易有限公司")
