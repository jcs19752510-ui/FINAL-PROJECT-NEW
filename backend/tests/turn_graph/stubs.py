"""무거운 AI 의존성(faster-whisper, sentence-transformers, piper 등)이 없는 경량 테스트 venv 용 스텁
(docs/harness/test-infra.md §2.2 와 같은 방식). langchain / langgraph 는 스텁하지 않는다 — 진짜를 검증한다."""

import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock

_NAMES = ("faster_whisper", "sentence_transformers", "librosa", "piper", "av", "torch", "deepface")


class _Stub(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return MagicMock()


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        if name.split(".")[0] in _NAMES:
            return importlib.machinery.ModuleSpec(name, self, is_package=True)

    def create_module(self, spec):
        m = _Stub(spec.name)
        m.__path__ = []
        return m

    def exec_module(self, module):
        pass


def install() -> None:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        sys.meta_path.insert(0, _Finder())
