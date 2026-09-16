from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session

from app import skills_service
from app.db import get_session
from app.schemas import SkillOut

router = APIRouter(prefix="/skills", tags=["skills"])


@router.post("/upload", response_model=SkillOut)
async def upload_skill(file: UploadFile, session: Session = Depends(get_session)) -> SkillOut:
    try:
        skill = await skills_service.upload_skill(session, file)
    except skills_service.SkillValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SkillOut.model_validate(skill, from_attributes=True)


@router.get("", response_model=list[SkillOut])
def list_skills(session: Session = Depends(get_session)) -> list[SkillOut]:
    skills = skills_service.list_skills(session)
    return [SkillOut.model_validate(s, from_attributes=True) for s in skills]
