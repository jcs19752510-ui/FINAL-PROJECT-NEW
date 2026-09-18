flowchart TD

    subgraph P1["① 목적 (Why)"]
        A1[채용 병목 해결<br/>일정조율·주관적평가 문제]
        A2[구직자 훈련도구 제공<br/>시간·장소 제약 없는 연습]
        A1 --> A2
        A2 --> A3[AI 면접관 서비스 구현]
    end

    subgraph P2["② 방법 (How - 기획/설계)"]
        B1[요구사항 정의<br/>SRS 작성]
        B2[아키텍처 설계<br/>FastAPI+STT+LLM+TTS]
        B3[MVP 스코프 확정<br/>7주 내 구현가능 범위로 축소]
        B1 --> B2 --> B3
    end

    subgraph P3["③ 셋팅 (환경 구축)"]
        C1[Python 가상환경<br/>FastAPI 프로젝트 초기화]
        C2[DB 구축<br/>PostgreSQL + Redis]
        C3[외부 API 키 발급<br/>OpenAI Whisper·LLM·TTS]
        C4[Git 저장소 및<br/>브랜치 전략 수립]
        C1 --> C2 --> C3 --> C4
    end

    subgraph P4["④ 개발 (Implementation)"]
        D1[백엔드 코어 API<br/>인증·세션·면접방 관리]
        D2[음성 파이프라인<br/>STT 연동]
        D3[LLM 오케스트레이터<br/>질문생성·꼬리질문·평가]
        D4[TTS 연동<br/>AI 면접관 음성 응답]
        D5[프론트엔드 UI<br/>면접장 화면·코드에디터]
        D6[감정/표정 분석<br/>DeepFace 연동]
        D7[리포트 생성 로직<br/>STAR 기반 평가서]
        D1 --> D2 --> D3 --> D4
        D1 --> D5
        D2 --> D6
        D3 --> D7
    end

    subgraph P5["⑤ 테스트 (QA)"]
        E1[단위 테스트<br/>API·모듈별 검증]
        E2[통합 테스트<br/>음성→LLM→응답 전체흐름]
        E3[시나리오 테스트<br/>실제 면접 상황 재현]
        E4[AI 응답 품질 검증<br/>루브릭 일치도 확인]
        E1 --> E2 --> E3 --> E4
    end

    subgraph P6["⑥ 운영 (Deploy & Operate)"]
        F1[배포<br/>Docker 컨테이너화]
        F2[모니터링<br/>API 사용량·에러 로그]
        F3[사용자 피드백 수집]
        F4[개선 및 다음 버전 계획]
        F1 --> F2 --> F3 --> F4
    end

    P1 --> P2 --> P3 --> P4 --> P5 --> P6
