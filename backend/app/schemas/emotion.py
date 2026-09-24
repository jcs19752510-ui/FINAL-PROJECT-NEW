from pydantic import BaseModel


class EmotionAnalysisOut(BaseModel):
    dominant_emotion: str
    scores: dict[str, float]
    face_confidence: float
    disclaimer: str
