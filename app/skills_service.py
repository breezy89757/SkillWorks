"""Skill 上傳流程，對應 spec §5。

刻意不做的事（照抄 spec §2 / §5）：
- 不解析、不驗證 skill 附帶的 requirements.txt / pyproject.toml
- 不安裝任何套件
- 不做 per-skill venv / 容器隔離
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml
from fastapi import UploadFile
from sqlmodel import Session, select

from app.config import settings
from app.models import Skill

_FRONTMATTER_DELIM = "---"


class SkillValidationError(Exception):
    pass


def _extract_frontmatter(skill_md_text: str) -> dict:
    lines = skill_md_text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
        raise SkillValidationError("SKILL.md 缺少 YAML frontmatter（需以 --- 開頭）")
    try:
        end = lines[1:].index(_FRONTMATTER_DELIM) + 1
    except ValueError as exc:
        raise SkillValidationError("SKILL.md 的 YAML frontmatter 沒有結尾的 ---") from exc

    frontmatter_text = "\n".join(lines[1:end])
    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"SKILL.md frontmatter YAML 格式錯誤: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillValidationError("SKILL.md frontmatter 必須是一個 YAML mapping")
    return data


def _find_skill_md(extracted_dir: Path) -> Path:
    # 允許 zip 內容直接是 skill 檔案，或包一層資料夾（常見情況）
    direct = extracted_dir / "SKILL.md"
    if direct.exists():
        return direct

    candidates = list(extracted_dir.rglob("SKILL.md"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SkillValidationError("zip 裡找不到 SKILL.md")
    raise SkillValidationError(f"zip 裡有多個 SKILL.md，無法判斷 skill 根目錄: {candidates}")


def _has_scripts(skill_root: Path) -> bool:
    scripts_dir = skill_root / "scripts"
    return scripts_dir.is_dir() and any(scripts_dir.iterdir())


async def upload_skill(session: Session, file: UploadFile, owner: str = "") -> Skill:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise SkillValidationError("只接受 .zip 檔案")

    with tempfile.TemporaryDirectory(prefix="skill_upload_") as tmp_str:
        tmp_dir = Path(tmp_str)
        zip_path = tmp_dir / "upload.zip"
        content = await file.read()
        zip_path.write_bytes(content)

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _safe_extract(zf, extract_dir)
        except zipfile.BadZipFile as exc:
            raise SkillValidationError("無法解壓縮，檔案不是合法的 zip") from exc

        skill_md_path = _find_skill_md(extract_dir)
        skill_root = skill_md_path.parent
        frontmatter = _extract_frontmatter(skill_md_path.read_text(encoding="utf-8"))

        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not name or not isinstance(name, str):
            raise SkillValidationError("SKILL.md frontmatter 缺少必填欄位 name")
        if not description or not isinstance(description, str):
            raise SkillValidationError("SKILL.md frontmatter 缺少必填欄位 description")

        skill = Skill(name=name, description=description, owner=owner, path="")
        dest_dir = settings.skills_storage_dir / skill.id
        shutil.copytree(skill_root, dest_dir)

        skill.path = str(dest_dir)
        skill.has_scripts = _has_scripts(dest_dir)

        session.add(skill)
        session.commit()
        session.refresh(skill)
        return skill


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """避免 zip slip：確保所有成員都解到 dest 底下。"""
    dest_resolved = dest.resolve()
    for member in zf.namelist():
        member_path = (dest / member).resolve()
        if dest_resolved not in member_path.parents and member_path != dest_resolved:
            raise SkillValidationError(f"zip 內含不安全的路徑: {member}")
    zf.extractall(dest)


def list_skills(session: Session) -> list[Skill]:
    return list(session.exec(select(Skill).order_by(Skill.created_at.desc())))


def get_skills_by_ids(session: Session, skill_ids: list[str]) -> list[Skill]:
    if not skill_ids:
        return []
    skills = list(session.exec(select(Skill).where(Skill.id.in_(skill_ids))))
    # 依 skill_ids 的順序回傳，方便前端維持勾選順序
    by_id = {s.id: s for s in skills}
    return [by_id[i] for i in skill_ids if i in by_id]
