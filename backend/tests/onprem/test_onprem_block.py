"""온프리미스 모드(ONPREM_MODE) 외부 AI 호출 차단 내부 테스트.
- STT 라우터: 키가 있어도 온프리미스에서는 Deepgram 을 호출하지 않고 로컬 faster-whisper 로 처리
- 다층 방어: 라우터를 거치지 않는 직접 호출(Deepgram/OpenAI 비전/ElevenLabs)도 네트워크 전에 거부
- 롤백: ONPREM_MODE=false 면 이전 동작(키가 있으면 Deepgram 선시도, 실패 시 로컬 폴백) 그대로
실행: DATABASE_URL, JWT_SECRET_KEY 더미 환경변수 필요(설정 객체 로딩용, 실제 접속 없음)."""
import logging
import urllib.error

import pytest

from tests.turn_graph import stubs

stubs.install()

from app.core.config import Settings, settings  # noqa: E402
from app.services import stt_adapter_deepgram, stt_router, tts_adapter_elevenlabs, whiteboard_vision  # noqa: E402
from app.services.stt_engine import SttTranscriptionError  # noqa: E402
from app.services.tts_engine import TtsSynthesisError  # noqa: E402


@pytest.fixture
def router(monkeypatch):
    calls = {"deepgram": 0, "local": 0}

    def fake_deepgram(audio, key, content_type):
        calls["deepgram"] += 1
        return "deepgram-text"

    def fake_local(audio):
        calls["local"] += 1
        return "local-text"

    monkeypatch.setattr(stt_router, "transcribe_audio_deepgram", fake_deepgram)
    monkeypatch.setattr(stt_router, "transcribe_audio", fake_local)
    monkeypatch.setattr(stt_router, "_blocked_key_warned", False)
    return calls


def _cfg(monkeypatch, key, onprem):
    monkeypatch.setattr(settings, "deepgram_api_key", key)
    monkeypatch.setattr(settings, "onprem_mode", onprem)


def test_op01_key_present_onprem_uses_local_only(monkeypatch, router):
    _cfg(monkeypatch, "secret-key", True)
    assert stt_router.transcribe_audio_smart(b"x", "audio/wav") == "local-text"
    assert router == {"deepgram": 0, "local": 1}


def test_op02_no_key_onprem_uses_local(monkeypatch, router):
    _cfg(monkeypatch, None, True)
    assert stt_router.transcribe_audio_smart(b"x", None) == "local-text"
    assert router == {"deepgram": 0, "local": 1}


def test_op03_rollback_key_present_onprem_off_deepgram_first(monkeypatch, router):
    _cfg(monkeypatch, "secret-key", False)
    assert stt_router.transcribe_audio_smart(b"x", "audio/webm") == "deepgram-text"
    assert router == {"deepgram": 1, "local": 0}


def test_op04_rollback_deepgram_failure_falls_back_to_local(monkeypatch, router):
    _cfg(monkeypatch, "secret-key", False)

    def boom(audio, key, content_type):
        raise SttTranscriptionError("벤더 장애")

    monkeypatch.setattr(stt_router, "transcribe_audio_deepgram", boom)
    assert stt_router.transcribe_audio_smart(b"x", "audio/wav") == "local-text"
    assert router["local"] == 1


def test_op05_blocked_key_warning_logged_once(monkeypatch, router, caplog):
    _cfg(monkeypatch, "secret-key", True)
    with caplog.at_level(logging.WARNING, logger="app.services.stt_router"):
        for _ in range(3):
            stt_router.transcribe_audio_smart(b"x", "audio/wav")
    msgs = [r.message for r in caplog.records if "ONPREM_MODE로 차단" in r.message]
    assert len(msgs) == 1
    assert "secret-key" not in caplog.text  # 키 값은 로그에 남기지 않는다


def test_op06_no_warning_when_no_key(monkeypatch, router, caplog):
    _cfg(monkeypatch, None, True)
    with caplog.at_level(logging.WARNING, logger="app.services.stt_router"):
        stt_router.transcribe_audio_smart(b"x", "audio/wav")
    assert "ONPREM_MODE" not in caplog.text


# --- 다층 방어: 직접 호출도 네트워크 전에 거부 -------------------------------------------
@pytest.fixture
def net(monkeypatch):
    seen = []

    def fake_urlopen(request, timeout=None):
        seen.append(getattr(request, "full_url", str(request)))
        raise urllib.error.URLError("네트워크 차단 시뮬레이션")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return seen


def test_op07_deepgram_adapter_direct_call_blocked(monkeypatch, net):
    monkeypatch.setattr(settings, "onprem_mode", True)
    with pytest.raises(SttTranscriptionError, match="온프리미스"):
        stt_adapter_deepgram.transcribe_audio_deepgram(b"x", "key", "audio/wav")
    assert net == []


def test_op08_openai_vision_direct_call_blocked(monkeypatch, net):
    monkeypatch.setattr(settings, "onprem_mode", True)
    with pytest.raises(whiteboard_vision.VisionAnalysisError, match="온프리미스"):
        whiteboard_vision.analyze_diagram_with_vision(b"\x89PNG", "key")
    assert net == []


def test_op09_elevenlabs_direct_call_blocked(monkeypatch, net):
    monkeypatch.setattr(settings, "onprem_mode", True)
    engine = tts_adapter_elevenlabs.ElevenLabsTTSEngine(api_key="key", voice_id="v")
    with pytest.raises(TtsSynthesisError, match="온프리미스"):
        engine.synthesize("안녕하세요")
    assert net == []


def test_op10_rollback_adapters_reach_network_layer(monkeypatch, net):
    """ONPREM_MODE=false 면 가드가 개입하지 않아 어댑터가 실제로 네트워크 호출을 시도한다(회귀)."""
    monkeypatch.setattr(settings, "onprem_mode", False)
    with pytest.raises(SttTranscriptionError):
        stt_adapter_deepgram.transcribe_audio_deepgram(b"x", "key", "audio/wav")
    assert any("api.deepgram.com" in u for u in net)
    engine = tts_adapter_elevenlabs.ElevenLabsTTSEngine(api_key="key", voice_id="v")
    with pytest.raises(Exception):  # noqa: B017 — 네트워크 시뮬레이션 오류가 어댑터 예외로 승격되는지만 본다
        engine.synthesize("안녕")
    assert any("elevenlabs" in u for u in net)


# --- 설정 ------------------------------------------------------------------------------
def test_op11_settings_default_true_and_env_override(monkeypatch):
    monkeypatch.delenv("ONPREM_MODE", raising=False)
    assert Settings().onprem_mode is True
    monkeypatch.setenv("ONPREM_MODE", "false")
    assert Settings().onprem_mode is False


def test_op12_settings_invalid_value_rejected(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("ONPREM_MODE", "maybe")
    with pytest.raises(ValidationError):
        Settings()


def test_op13_email_is_not_blocked_by_onprem_mode():
    """메일(SMTP)은 지원자에게 전달해야 하는 외부 통신이라 온프리미스 차단 대상이 아니다(사용자 지시)."""
    import inspect

    from app.services import email_service

    assert "onprem_mode" not in inspect.getsource(email_service)
