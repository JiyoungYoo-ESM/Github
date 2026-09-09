"""SCM AI assistant chat grounded on a previously generated result workbook."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from backend.ai import build_ai_prompt, build_context_from_output_excel, call_ollama
from backend.config import JOB_ID_PATTERN
from backend.schemas import AiChatRequest, AiChatResponse
from backend.services.audit import write_audit_event
from backend.services.storage import (
    ensure_storage_dirs,
    output_path_for_job,
    verify_download_token,
)

router = APIRouter()


@router.post("/api/ai/chat", response_model=AiChatResponse)
async def ai_chat(request_body: AiChatRequest, request: Request) -> AiChatResponse:
    ensure_storage_dirs()
    job_id = request_body.job_id.strip()
    token = request_body.token.strip()
    question = request_body.question.strip()
    if not JOB_ID_PATTERN.fullmatch(job_id):
        write_audit_event("ai_chat_failed", request, job_id=job_id, reason="invalid_job_id")
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    if not question:
        write_audit_event("ai_chat_failed", request, job_id=job_id, reason="empty_question")
        raise HTTPException(status_code=400, detail="질문 내용을 입력해 주세요.")
    try:
        verify_download_token(
            job_id,
            token,
            expected_username=request.state.current_user.username,
            expected_entity_code=str(request.state.entity_code),
        )
    except HTTPException as exc:
        write_audit_event(
            "ai_chat_failed",
            request,
            job_id=job_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    output_path = output_path_for_job(job_id)

    try:
        context = await run_in_threadpool(build_context_from_output_excel, output_path)
        prompt = build_ai_prompt(question, context)
        answer, model = await run_in_threadpool(call_ollama, prompt)
    except RuntimeError as exc:
        write_audit_event("ai_chat_failed", request, job_id=job_id, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        write_audit_event("ai_chat_failed", request, job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 중 오류가 발생했습니다: {exc}") from exc

    write_audit_event(
        "ai_chat_succeeded",
        request,
        job_id=job_id,
        model=model,
        question_length=len(question),
        context_summary=context.context_summary,
    )

    return AiChatResponse(
        job_id=job_id,
        answer=answer,
        model=model,
        context_summary=context.context_summary,
    )
