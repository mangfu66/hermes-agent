import pytest

from agent.gemini_cloudcode_adapter import (
    ANTIGRAVITY_DAILY_ENDPOINT,
    GeminiCloudCodeClient,
    ProjectContext,
)


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.headers = {}
        self.text = ""

    def json(self):
        return {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "OK"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {},
            }
        }


class _FakeHTTP:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(200)

    def close(self):
        return None


@pytest.fixture
def antigravity_client(monkeypatch):
    monkeypatch.setattr(
        "agent.google_antigravity_oauth.get_valid_access_token",
        lambda: "ya29.antigravity",
    )
    client = GeminiCloudCodeClient(ide_type="ANTIGRAVITY")
    client._ensure_project_context = lambda access_token, model: ProjectContext(
        project_id="cool-environs-jdt91",
        managed_project_id="",
        tier_id="standard-tier",
        source="test",
    )
    client._http = _FakeHTTP()
    return client


def test_antigravity_claude_uses_daily_endpoint_and_headers(antigravity_client):
    resp = antigravity_client.chat.completions.create(
        model="claude-opus-4-6-thinking",
        messages=[{"role": "user", "content": "Reply with exactly OK and nothing else."}],
    )
    call = antigravity_client._http.calls[0]
    assert call["url"] == f"{ANTIGRAVITY_DAILY_ENDPOINT}/v1internal:generateContent"
    assert call["json"]["requestType"] == "agent"
    assert call["json"]["userAgent"] == "antigravity"
    assert call["json"]["requestId"].startswith("agent-")
    assert call["headers"]["User-Agent"].startswith("antigravity/")
    assert call["headers"]["anthropic-beta"] == "interleaved-thinking-2025-05-14"
    assert resp.choices[0].message.content == "OK"


def test_antigravity_gemini_omits_anthropic_beta(antigravity_client):
    antigravity_client.chat.completions.create(
        model="gemini-3.1-pro-high",
        messages=[{"role": "user", "content": "Reply with exactly OK and nothing else."}],
    )
    call = antigravity_client._http.calls[0]
    assert call["url"] == f"{ANTIGRAVITY_DAILY_ENDPOINT}/v1internal:generateContent"
    assert call["headers"]["User-Agent"].startswith("antigravity/")
    assert "anthropic-beta" not in call["headers"]
