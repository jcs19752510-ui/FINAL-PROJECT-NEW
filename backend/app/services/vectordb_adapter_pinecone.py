"""벡터DB 벤더 어댑터 — Pinecone (원안 §4.1, 2026-09-22 사용자 승인, unit-32).

**미검증 코드임을 명시**(다른 어댑터 파일과 동일 원칙). Pinecone API 키가
없어 실제 호출 검증 못함.

**중요한 맥락**: ②비교표는 이 항목을 이미 "일치"로 판정했다 — 원안 자체가
Pinecone(주)과 pgvector(대안)를 함께 제시했고, 실제 구현(`rag_engine.py`)이
그 인정된 대안(pgvector)을 채택했기 때문이다(DEC-005). 즉 **이 어댑터를
실제로 연결해도 "더 정합해지는" 것이 아니라 "이미 정합한 것을 유료 서비스로
바꾸는" 선택**이다 — 예산이 있고 Pinecone 고유 기능(예: 매니지드 확장성)이
필요할 때만 가치가 있다. 인수인계 시 이 점을 반드시 전달할 것.

`app/services/rag_engine.py`의 `search_similar_questions()`와 동일한 반환
계약(Question 리스트)을 흉내 내려면 실제로는 Pinecone에 저장된 메타데이터에서
`Question` 객체를 재구성해야 하는데, 이는 Pinecone 쪽에 질문 원문/카테고리
등을 메타데이터로 동기화하는 별도 인덱싱 파이프라인이 선행되어야 한다 —
이 유닛은 그 인덱싱 파이프라인 없이 "임베딩 upsert/query"라는 가장 기본적인
클라이언트 호출부만 준비했다.
"""
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


class PineconeQueryError(Exception):
    pass


class PineconeClient:
    """Pinecone REST API(서버리스 인덱스 기준, 공식 문서 형태 — 실측 미확인)를
    감싼 최소 클라이언트. 공식 `pinecone-client` SDK를 쓰지 않고 REST 직접
    호출로 구현했다 — 이 프로젝트의 다른 벤더 어댑터(Deepgram/ElevenLabs)와
    동일하게 "표준 라이브러리 urllib만으로 의존성을 최소화"하는 기존 관례
    (`llm_engine.py`의 OpenAI 호환 호출 방식과 동일 스타일)를 따른 것.
    """

    def __init__(self, api_key: str, index_host: str) -> None:
        self._api_key = api_key
        self._index_host = index_host.rstrip("/")

    def _request(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self._index_host}{path}",
            data=data,
            headers={"Api-Key": self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PineconeQueryError("Pinecone 요청에 실패했습니다(미검증 어댑터).") from exc

    def upsert(self, vector_id: str, embedding: list[float], metadata: dict) -> None:
        """`rag_engine.embed_text()`가 만드는 384차원 임베딩을 그대로 넣을 수
        있다(같은 임베딩 모델을 쓴다는 전제 — Pinecone 인덱스 자체를
        384차원으로 생성해야 함, 인프라 설정 별도 필요).
        """
        self._request("/vectors/upsert", {"vectors": [{"id": vector_id, "values": embedding, "metadata": metadata}]})

    def query(self, embedding: list[float], top_k: int = 3) -> list[dict]:
        """`rag_engine.search_similar_questions()`가 하는 pgvector 코사인거리
        검색과 동등한 역할 — 반환값은 Pinecone의 원시 매치 리스트(id, score,
        metadata)이며, 호출부가 `Question` 객체로 재구성해야 한다(모듈
        docstring 참고, 이 어댑터가 그 재구성까지는 하지 않음).
        """
        result = self._request("/query", {"vector": embedding, "topK": top_k, "includeMetadata": True})
        return result.get("matches", [])
