from __future__ import annotations

from cctv.config.models import AgentConfig, CameraConfig, SectorConfig

UNASSIGNED_SECTOR_ID = "unassigned"
UNASSIGNED_SECTOR_NAME = "Unassigned"


def unassigned_sector() -> SectorConfig:
    return SectorConfig(id=UNASSIGNED_SECTOR_ID, name=UNASSIGNED_SECTOR_NAME, enabled=True)


def sectors_by_id(sectors: list[SectorConfig]) -> dict[str, SectorConfig]:
    return {sector.id.lower(): sector for sector in sectors}


def normalize_agent_config(config: AgentConfig) -> AgentConfig:
    """Ensure sectors exist and cameras reference valid sector ids."""
    sectors = list(config.sectors)
    by_id = sectors_by_id(sectors)
    if UNASSIGNED_SECTOR_ID not in by_id:
        sectors.append(unassigned_sector())
        by_id[UNASSIGNED_SECTOR_ID] = sectors[-1]

    cameras: list[CameraConfig] = []
    for camera in config.cameras:
        sector_id = camera.sector_id or UNASSIGNED_SECTOR_ID
        if sector_id.lower() not in by_id:
            sector_id = UNASSIGNED_SECTOR_ID
        cameras.append(camera.model_copy(update={"sector_id": sector_id}))

    return config.model_copy(update={"sectors": sectors, "cameras": cameras})


def sector_for_camera(config: AgentConfig, camera: CameraConfig) -> SectorConfig | None:
    sector_id = (camera.sector_id or UNASSIGNED_SECTOR_ID).lower()
    return sectors_by_id(config.sectors).get(sector_id)


def is_camera_effective(config: AgentConfig, camera: CameraConfig) -> bool:
    sector = sector_for_camera(config, camera)
    if sector is None:
        return camera.enabled
    return sector.enabled and camera.enabled


def effective_cameras(config: AgentConfig) -> list[CameraConfig]:
    normalized = normalize_agent_config(config)
    return [camera for camera in normalized.cameras if is_camera_effective(normalized, camera)]


def validate_sector_references(config: AgentConfig) -> None:
    normalized = normalize_agent_config(config)
    known = {sector.id.lower() for sector in normalized.sectors}
    for camera in normalized.cameras:
        sector_id = (camera.sector_id or UNASSIGNED_SECTOR_ID).lower()
        if sector_id not in known:
            raise ValueError(
                f"Camera {camera.id!r} references unknown sector {camera.sector_id!r}."
            )


def validate_sector_removals(base: AgentConfig, current: AgentConfig) -> None:
    base_ids = {sector.id.lower() for sector in base.sectors}
    current_ids = {sector.id.lower() for sector in current.sectors}
    removed = base_ids - current_ids
    if not removed:
        return
    # Payloads that omit sectors still normalize to Unassigned; do not treat that as deletion.
    if not current.sectors:
        removed.discard(UNASSIGNED_SECTOR_ID)
    if not removed:
        return
    for camera in current.cameras:
        sector_id = (camera.sector_id or UNASSIGNED_SECTOR_ID).lower()
        if sector_id in removed:
            sector_name = next(
                (sector.name for sector in base.sectors if sector.id.lower() == sector_id),
                sector_id,
            )
            raise ValueError(
                f"Cannot remove sector {sector_name!r} while camera {camera.name!r} "
                f"({camera.id}) is still assigned to it."
            )
