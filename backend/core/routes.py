from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from core import schemas, service
from core.errors import Problem

router = APIRouter()


def current_user(request: Request):
    return service.authenticate(request.app.state.db, request.cookies.get("saarthi_session"))


def onboarded(user=Depends(current_user)):
    if user.onboarded_at is None:
        raise Problem(403, "onboarding_required", "Complete your profile first.")
    return user


def dependencies(request):
    return request.app.state.db, request.app.state.settings


@router.post("/auth/otp/request")
def request_otp(body: schemas.Phone):
    return {"phone": body.phone, "mock": True}


@router.post("/auth/otp/verify")
def verify_otp(body: schemas.Verify, request: Request, response: Response):
    factory, settings = dependencies(request)
    token, user = service.login(factory, settings, body.phone)
    response.set_cookie(
        "saarthi_session",
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        path="/",
    )
    return {"user": user, "onboarding_required": user["onboarding_required"]}


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, user=Depends(current_user)):
    service.logout(request.app.state.db, user.id, request.cookies["saarthi_session"])
    response.delete_cookie(
        "saarthi_session",
        path="/",
        secure=request.app.state.settings.secure_cookie,
        httponly=True,
        samesite="lax",
    )


@router.get("/me")
def me(user=Depends(current_user)):
    return service.public_user(user)


@router.patch("/me")
def update_me(body: schemas.Profile, request: Request, user=Depends(current_user)):
    return service.profile(request.app.state.db, user.id, body.model_dump())


@router.get("/conversations")
def conversations(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    before: Annotated[str | None, Query(max_length=100)] = None,
    user=Depends(onboarded),
):
    return service.list_conversations(request.app.state.db, user.id, limit, before)


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, request: Request, user=Depends(onboarded)):
    return service.get_conversation(request.app.state.db, user.id, conversation_id)


@router.post("/conversations", status_code=201)
async def create_conversation(
    body: schemas.CreateConversation, request: Request, user=Depends(onboarded)
):
    return await service.generate(*dependencies(request), user.id, body.id)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def send_message(
    conversation_id: UUID, body: schemas.Send, request: Request, user=Depends(onboarded)
):
    return await service.generate(*dependencies(request), user.id, conversation_id, body)


@router.post("/conversations/{conversation_id}/end")
async def end(conversation_id: UUID, request: Request, user=Depends(onboarded)):
    return await service.end_conversation(*dependencies(request), user.id, conversation_id)


@router.get("/knowledge")
def knowledge(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    after: UUID | None = None,
    user=Depends(onboarded),
):
    return service.list_knowledge(request.app.state.db, user.id, limit, after)


@router.post("/knowledge", status_code=201)
def add_knowledge(body: schemas.KnowledgeCreate, request: Request, user=Depends(onboarded)):
    return service.edit_knowledge(request.app.state.db, user.id, body.model_dump())


@router.patch("/knowledge/{record_id}")
def update_knowledge(
    record_id: UUID, body: schemas.KnowledgePatch, request: Request, user=Depends(onboarded)
):
    return service.edit_knowledge(
        request.app.state.db, user.id, body.model_dump(exclude_unset=True), record_id
    )


@router.delete("/knowledge/{record_id}", status_code=204)
def delete_knowledge(record_id: UUID, request: Request, user=Depends(onboarded)):
    service.edit_knowledge(request.app.state.db, user.id, {}, record_id, delete=True)
