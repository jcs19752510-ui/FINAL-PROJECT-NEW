# 2026-10-16: alembic/env.py가 `app.models.*`를 임포트하면 이 패키지가 먼저 실행되므로, 여기서
# 새 모델을 등록해 두면 env.py를 수정하지 않고도 Base.metadata에 user_identities가 포함된다.
from app.models.user_identity import UserIdentity  # noqa: F401
