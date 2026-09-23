# unit-32 구현 노트 — 유료 API 벤더 어댑터 3종 (미검증, 코드만)

- 작성 에이전트: 본 세션, 작성일: 2026-09-22
- 대상: TTS→ElevenLabs, STT→Deepgram Nova-2, 벡터DB→Pinecone (③ 매트릭스
  "가능(소)" 3개 항목)
- **2026-09-22 합의 사항 그대로**: "API 키 없이는 코드/어댑터만 준비, 실제
  연동 테스트는 키를 받은 뒤" — 이번 유닛은 정확히 그 범위만 수행했다.

## 1. 구현 범위 — 전부 미검증

- `backend/app/services/tts_adapter_elevenlabs.py`: `ITTSEngine` 인터페이스
  구현. MP3 반환(Piper의 WAV와 포맷 다름 — 교체 시 파이프라인 조정 필요).
- `backend/app/services/stt_adapter_deepgram.py`: `stt_engine.transcribe_audio()`
  와 동일 시그니처. 배치 호출만(스트리밍 아님).
- `backend/app/services/vectordb_adapter_pinecone.py`: upsert/query 최소
  클라이언트. **`rag_engine.py`의 `Question` 객체 재구성은 하지 않음** —
  별도 인덱싱 동기화 파이프라인이 선행되어야 함.

## 2. 왜 실행 테스트를 하지 않았는가 (사용자 승인 범위 그대로)

API 키가 없다 — 이건 코드 품질의 문제가 아니라 자원의 문제다. **이 3개
어댑터는 코드 리뷰만 거쳤고 단 한 번도 실제 벤더 서버와 통신한 적이 없다.**
이 세션 전체가 강조해온 "실제로 실행해서 검증한 것만 완료로 표시" 원칙에
따라, ③ 매트릭스에 "완료"로 표시하지 않고 **"코드 준비 완료 — 미검증"**으로
구분한다.

## 3. 벡터DB(Pinecone) 관련 중요 맥락

②비교표는 "벡터DB" 항목을 이미 "일치"로 판정했다(원안이 pgvector를 공식
대안으로 인정, DEC-005). Pinecone 어댑터를 실제로 붙이는 것은 **"틀린 것을
고치는" 작업이 아니라 "이미 맞는 것을 유료 서비스로 바꾸는" 선택**이다 —
인수인계 시 이 우선순위 판단을 반드시 전달할 것.

## 4. 실제 연결 시 체크리스트(인수인계)

- [ ] 각 벤더 API 키 발급 및 `.env`/K8s Secret에 등록
- [ ] 실제 호출 1회 이상 성공시켜 응답 스키마가 코드의 가정과 일치하는지
  확인(특히 Deepgram의 `results.channels[0].alternatives[0].transcript`
  경로, ElevenLabs의 MP3 포맷)
- [ ] `get_tts_engine()`/`transcribe_audio()`/`rag_engine.py`의 팩토리·호출부를
  실제로 교체
- [ ] 06단계 수준의 정식 테스트(경계값/에러/타임아웃) 재실행
