from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    # [2026-09-30 사용자 지시로 보안 강화] 원래는 candidate/recruiter 둘 다 허용했으나,
    # 인증 없이 누구나 role=recruiter로 자가가입해 전체 지원자 이력서·개인정보에 접근할
    # 수 있는 실제 보안 구멍이었다(이 공개 엔드포인트에 인증 검사가 전혀 없었음). 이제
    # 이 공개 엔드포인트는 candidate만 받고, recruiter 계정은 별도의 보호된 엔드포인트
    # (`POST /recruiter/recruiters`, 기존 recruiter 로그인 필수)로만 만들 수 있다.
    role: Literal["candidate"] = "candidate"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
