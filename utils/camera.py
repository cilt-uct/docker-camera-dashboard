from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.sql import func as sql_func
from typing import Optional, List

from utils.models import Camera
from utils.schemas import CameraCreate, CameraUpdate

class CameraRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, camera_data: CameraCreate) -> Camera:
        """Create a new camera"""
        camera = Camera(**camera_data.model_dump())
        self.db.add(camera)
        await self.db.flush()
        await self.db.refresh(camera)
        return camera

    async def upsert(self, camera_data: CameraCreate) -> Camera:
        """
        Insert a new camera or update existing one based on name.
        Returns the camera (either existing or newly created).
        """
        # Check if camera exists
        existing = await self.get_by_name(camera_data.name)

        if existing:
            # Update existing camera with new data
            update_data = CameraUpdate(
                url=camera_data.url,
                enabled=camera_data.enabled
            )
            return await self.update(existing.id, update_data)
        else:
            # Create new camera
            return await self.create(camera_data)

    async def upsert_many(self, cameras_data: List[CameraCreate]) -> List[Camera]:
        """
        Insert or update multiple cameras efficiently using MySQL's ON DUPLICATE KEY UPDATE.
        This is more efficient than doing individual upserts.
        """
        if not cameras_data:
            return []

        # Prepare the data for bulk insert
        values = [camera.model_dump() for camera in cameras_data]

        # Use MySQL's INSERT ... ON DUPLICATE KEY UPDATE
        stmt = mysql_insert(Camera).values(values)

        # Define what to update on duplicate key
        update_stmt = stmt.on_duplicate_key_update(
            url=stmt.inserted.url,
            enabled=stmt.inserted.enabled,
            updated_at=sql_func.now()
        )

        # Execute the upsert
        await self.db.execute(update_stmt)
        await self.db.flush()

        # Fetch all cameras that were just upserted
        names = [camera.name for camera in cameras_data]
        result = await self.db.execute(
            select(Camera).where(Camera.name.in_(names))
        )
        cameras = list(result.scalars().all())

        # Refresh all cameras to ensure they have latest data
        for camera in cameras:
            await self.db.refresh(camera)

        return cameras

    async def get_by_id(self, camera_id: int) -> Optional[Camera]:
        """Get camera by ID"""
        result = await self.db.execute(
            select(Camera).where(Camera.id == camera_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Camera]:
        """Get camera by name"""
        result = await self.db.execute(
            select(Camera).where(Camera.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 200,
        enabled_only: bool = False
    ) -> List[Camera]:
        """Get all cameras with pagination"""
        query = select(Camera)

        if enabled_only:
            query = query.where(Camera.enabled == True) # noqa: E712

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(
        self,
        camera_id: int,
        update_data: CameraUpdate
    ) -> Optional[Camera]:
        """Update camera"""
        # Filter out None values
        update_dict = {
            k: v for k, v in update_data.model_dump().items()
            if v is not None
        }

        if not update_dict:
            return await self.get_by_id(camera_id)

        # Update
        await self.db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(**update_dict)
        )
        await self.db.flush()

        # Return updated camera
        return await self.get_by_id(camera_id)

    async def update_last_attempt(
        self,
        camera_id: int,
        timestamp
    ) -> None:
        """Update last capture attempt timestamp"""
        await self.db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(last_capture_attempt=timestamp)
        )
        await self.db.flush()

    async def update_last_seen(
        self,
        camera_id: int,
        timestamp
    ) -> None:
        """Update last seen alive timestamp"""
        await self.db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(last_capture_completed=timestamp)
        )
        await self.db.flush()

    async def update_last_timelapse_run(
        self,
        camera_id: int,
        timestamp
    ) -> None:
        """Update last seen alive timestamp"""
        await self.db.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(last_timelapse_run=timestamp)
        )
        await self.db.flush()

    async def delete(self, camera_id: int) -> bool:
        """Delete camera"""
        result = await self.db.execute(
            delete(Camera).where(Camera.id == camera_id)
        )
        await self.db.flush()
        return result.rowcount > 0
