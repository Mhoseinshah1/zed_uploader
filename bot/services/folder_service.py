from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Folder, StoredFile


async def create_folder(session: AsyncSession, owner_id: int, name: str) -> Folder:
    folder = Folder(owner_id=owner_id, name=name.strip()[:255])
    session.add(folder)
    await session.commit()
    await session.refresh(folder)
    return folder


async def rename_folder(session: AsyncSession, folder: Folder, name: str) -> None:
    folder.name = name.strip()[:255]
    await session.commit()


async def delete_folder(session: AsyncSession, folder: Folder) -> None:
    # Files keep existing; folder_id is set NULL by the FK ondelete rule.
    await session.delete(folder)
    await session.commit()


async def get_folder(session: AsyncSession, folder_id: int) -> Optional[Folder]:
    result = await session.execute(select(Folder).where(Folder.id == folder_id))
    return result.scalar_one_or_none()


async def list_folders(session: AsyncSession, owner_id: int) -> list[Folder]:
    result = await session.execute(
        select(Folder).where(Folder.owner_id == owner_id).order_by(Folder.name)
    )
    return list(result.scalars().all())


async def move_file_to_folder(session: AsyncSession, stored: StoredFile, folder_id: Optional[int]) -> None:
    stored.folder_id = folder_id
    await session.commit()


async def get_files_in_folder(
    session: AsyncSession,
    owner_id: int,
    folder_id: Optional[int],
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[StoredFile], int]:
    q = select(StoredFile).where(
        StoredFile.owner_id == owner_id,
        StoredFile.is_deleted == False,  # noqa: E712
    )
    if folder_id is None:
        q = q.where(StoredFile.folder_id.is_(None))
    else:
        q = q.where(StoredFile.folder_id == folder_id)
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = await session.execute(
        q.order_by(StoredFile.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), total


async def count_files_in_folder(session: AsyncSession, owner_id: int, folder_id: int) -> int:
    return (await session.execute(
        select(func.count()).select_from(StoredFile).where(
            StoredFile.owner_id == owner_id, StoredFile.folder_id == folder_id
        )
    )).scalar_one()
