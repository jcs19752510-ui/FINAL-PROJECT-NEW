"""테스트용 PDF 생성 — reportlab + 한글 폰트(WenQuanYi Zen Hei). 폰트가 없으면 호출 측이 skip 한다."""
import io
import os

FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def make_pdf(lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    if not os.path.exists(FONT):
        raise FileNotFoundError(FONT)
    pdfmetrics.registerFont(TTFont("KR", FONT, subfontIndex=0))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("KR", 11)
    y = 800
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 18
        if y < 40:
            c.showPage()
            c.setFont("KR", 11)
            y = 800
    c.save()
    return buf.getvalue()


def blank_pdf() -> bytes:
    """글자가 전혀 없는 PDF(스캔본 흉내)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.rect(50, 50, 200, 200)
    c.save()
    return buf.getvalue()


SAMPLE = [
    "홍길동 백엔드 개발자",
    "경력 2019.03 ~ 2023.08 주식회사 한빛소프트 백엔드 개발 4년차",
    "결제 시스템 MSA 전환 프로젝트 설계 및 구현, Kafka 기반 이벤트 처리",
    "Python FastAPI Redis PostgreSQL 기반 주문 API 개발 및 운영",
    "쿠버네티스 환경에서 Docker 이미지 배포 파이프라인 구축 (CI/CD)",
    "대용량 트래픽 대응을 위한 캐시 도입으로 응답속도 개선",
    "기술: Python, Java, Spring, AWS, Docker, Kubernetes, Git",
]
