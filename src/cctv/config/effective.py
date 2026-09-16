from __future__ import annotations

from cctv.config.models import AgentConfig, CameraConfig, LocationConfig, SectorConfig

UNASSIGNED_SECTOR_ID = "unassigned"
UNASSIGNED_SECTOR_NAME = "Unassigned"
UNASSIGNED_LOCATION_ID = "unassigned"
UNASSIGNED_LOCATION_NAME = "Unassigned"


def unassigned_sector() -> SectorConfig:
    return SectorConfig(id=UNASSIGNED_SECTOR_ID, name=UNASSIGNED_SECTOR_NAME, enabled=True)


def unassigned_location_id(sector_id: str) -> str:
    if sector_id.lower() == UNASSIGNED_SECTOR_ID:
        return UNASSIGNED_LOCATION_ID
    return f"{sector_id}_unassigned"


def unassigned_location(sector_id: str) -> LocationConfig:
    return LocationConfig(
        id=unassigned_location_id(sector_id),
        name=UNASSIGNED_LOCATION_NAME,
        sector_id=sector_id,
        enabled=True,
    )


def sectors_by_id(sectors: list[SectorConfig]) -> dict[str, SectorConfig]:
    return {sector.id.lower(): sector for sector in sectors}


def locations_by_id(locations: list[LocationConfig]) -> dict[str, LocationConfig]:
    return {location.id.lower(): location for location in locations}


def normalize_agent_config(config: AgentConfig) -> AgentConfig:
    """Ensure sectors/locations exist and cameras reference valid ids."""
    sectors = list(config.sectors)
    sector_map = sectors_by_id(sectors)
    if UNASSIGNED_SECTOR_ID not in sector_map:
        sectors.append(unassigned_sector())
        sector_map[UNASSIGNED_SECTOR_ID] = sectors[-1]

    locations = []
    for location in config.locations:
        sector_id = location.sector_id or UNASSIGNED_SECTOR_ID
        if sector_id.lower() not in sector_map:
            sector_id = UNASSIGNED_SECTOR_ID
        locations.append(location.model_copy(update={"sector_id": sector_id}))
    location_map = locations_by_id(locations)

    needed_unassigned: set[str] = set()
    cameras: list[CameraConfig] = []
    for camera in config.cameras:
        sector_id = camera.sector_id or UNASSIGNED_SECTOR_ID
        if sector_id.lower() not in sector_map:
            sector_id = UNASSIGNED_SECTOR_ID

        location_id = camera.location_id
        if location_id is None or location_id.lower() not in location_map:
            needed_unassigned.add(sector_id)
            location_id = unassigned_location_id(sector_id)
        else:
            location = location_map[location_id.lower()]
            sector_id = location.sector_id or sector_id

        cameras.append(
            camera.model_copy(update={"sector_id": sector_id, "location_id": location_id})
        )

    for sector_id in needed_unassigned:
        key = unassigned_location_id(sector_id).lower()
        if key not in location_map:
            locations.append(unassigned_location(sector_id))
            location_map[key] = locations[-1]

    return config.model_copy(update={"sectors": sectors, "locations": locations, "cameras": cameras})


def sector_for_camera(config: AgentConfig, camera: CameraConfig) -> SectorConfig | None:
    sector_id = (camera.sector_id or UNASSIGNED_SECTOR_ID).lower()
    return sectors_by_id(config.sectors).get(sector_id)


def location_for_camera(config: AgentConfig, camera: CameraConfig) -> LocationConfig | None:
    location_id = camera.location_id
    if location_id is None:
        sector_id = camera.sector_id or UNASSIGNED_SECTOR_ID
        location_id = unassigned_location_id(sector_id)
    return locations_by_id(config.locations).get(location_id.lower())


def camera_gps(config: AgentConfig, camera: CameraConfig) -> tuple[float | None, float | None]:
    if camera.lat is not None and camera.lon is not None:
        return camera.lat, camera.lon
    location = location_for_camera(config, camera)
    if location is None:
        return None, None
    return location.lat, location.lon


def is_camera_effective(config: AgentConfig, camera: CameraConfig) -> bool:
    sector = sector_for_camera(config, camera)
    location = location_for_camera(config, camera)
    if sector is None or location is None:
        return camera.enabled
    return sector.enabled and location.enabled and camera.enabled


def effective_cameras(config: AgentConfig) -> list[CameraConfig]:
    normalized = normalize_agent_config(config)
    return [camera for camera in normalized.cameras if is_camera_effective(normalized, camera)]


def validate_sector_references(config: AgentConfig) -> None:
    normalized = normalize_agent_config(config)
    known_sectors = {sector.id.lower() for sector in normalized.sectors}
    known_locations = {location.id.lower() for location in normalized.locations}
    for location in normalized.locations:
        sector_id = (location.sector_id or UNASSIGNED_SECTOR_ID).lower()
        if sector_id not in known_sectors:
            raise ValueError(
                f"Location {location.id!r} references unknown sector {location.sector_id!r}."
            )
    for camera in normalized.cameras:
        sector_id = (camera.sector_id or UNASSIGNED_SECTOR_ID).lower()
        if sector_id not in known_sectors:
            raise ValueError(
                f"Camera {camera.id!r} references unknown sector {camera.sector_id!r}."
            )
        location_id = (camera.location_id or unassigned_location_id(camera.sector_id or UNASSIGNED_SECTOR_ID)).lower()
        if location_id not in known_locations:
            raise ValueError(
                f"Camera {camera.id!r} references unknown location {camera.location_id!r}."
            )


def validate_location_removals(base: AgentConfig, current: AgentConfig) -> None:
    base_ids = {location.id.lower() for location in base.locations}
    current_ids = {location.id.lower() for location in current.locations}
    removed = base_ids - current_ids
    if not removed:
        return
    if not current.locations:
        removed.discard(UNASSIGNED_LOCATION_ID)
        for sector in base.sectors:
            removed.discard(unassigned_location_id(sector.id).lower())
    if not removed:
        return
    for camera in current.cameras:
        location_id = (
            camera.location_id
            or unassigned_location_id(camera.sector_id or UNASSIGNED_SECTOR_ID)
        ).lower()
        if location_id in removed:
            location_name = next(
                (
                    location.name
                    for location in base.locations
                    if location.id.lower() == location_id
                ),
                location_id,
            )
            raise ValueError(
                f"Cannot remove location {location_name!r} while camera {camera.name!r} "
                f"({camera.id}) is still assigned to it."
            )


def validate_sector_removals(base: AgentConfig, current: AgentConfig) -> None:
    base_ids = {sector.id.lower() for sector in base.sectors}
    current_ids = {sector.id.lower() for sector in current.sectors}
    removed = base_ids - current_ids
    if not removed:
        return
    if not current.sectors:
        removed.discard(UNASSIGNED_SECTOR_ID)
    if not removed:
        return
    for location in current.locations:
        sector_id = (location.sector_id or UNASSIGNED_SECTOR_ID).lower()
        if sector_id in removed:
            sector_name = next(
                (sector.name for sector in base.sectors if sector.id.lower() == sector_id),
                sector_id,
            )
            raise ValueError(
                f"Cannot remove sector {sector_name!r} while location {location.name!r} "
                f"({location.id}) is still assigned to it."
            )
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
