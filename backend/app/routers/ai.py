"""AI generation endpoints (optional, off unless configured).

`GET /api/ai/status` is public (booleans only) so the frontend can show/hide the
generate buttons. Text generation requires a logged-in host; the no-account flow
gets the same capability via the manage-token routes in routers/manage.py. This
keeps the LLM from being an open public proxy.
"""
from fastapi import APIRouter, Depends

from app import ai_service
from app.auth import get_current_user
from app.models import User
from app.schemas import AiStatus, AiTextRequest, AiTextResult

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status", response_model=AiStatus)
def ai_status():
    return AiStatus(llm=ai_service.llm_enabled(), image=ai_service.image_enabled())


@router.post("/text", response_model=AiTextResult)
async def generate_text(body: AiTextRequest, user: User = Depends(get_current_user)):
    return AiTextResult(text=await ai_service.text_from_request(body))
