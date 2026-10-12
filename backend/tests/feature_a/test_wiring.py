"""실제 운영 모듈에 새 기능이 연결됐는지(오타·미정의 이름·순환 import 포함) 확인하는 import/배선 테스트.
무거운 AI 패키지는 tests/turn_graph/stubs 로 대체한다(langchain·langgraph는 진짜)."""

import inspect

from tests.turn_graph import stubs

stubs.install()

from app.core.config import Settings  # noqa: E402


def test_wr01_main_imports_and_metrics_disabled_by_default(monkeypatch):
    monkeypatch.delenv("METRICS_ENABLED", raising=False)
    assert Settings().metrics_enabled is False
    from app import main

    assert not any(getattr(r, "path", None) == "/metrics" for r in main.app.routes)  # 기본은 노출 안 함


def test_wr02_metrics_setting_env_override(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "true")
    assert Settings().metrics_enabled is True


def test_wr03_interviews_module_uses_speech_rate_after_prosody():
    from app.api.v1 import interviews

    assert interviews.attach_speech_rate.__module__ == "app.services.speech_rate"
    src = inspect.getsource(interviews)
    assert src.index("analyze_prosody, audio_bytes") < src.index("attach_speech_rate(prosody_json, text)")


def test_wr04_tasks_uses_conversation_memory_and_speech_summary():
    from app.worker import tasks

    src = inspect.getsource(tasks)
    assert "conversation_memory.history_lines(" in src
    assert "summarize_speech_rate(" in src and '"speech_rate"' in src
    # 합산은 사용자 턴만, 그리고 정합성 보정 노트가 details_json을 덮어쓰지 않아야 한다
    assert "if t.speaker == Speaker.user" in src
    assert '{**details_json, "_server_consistency_override"' in src
    assert '{**output.details, "_server_consistency_override"' not in src
