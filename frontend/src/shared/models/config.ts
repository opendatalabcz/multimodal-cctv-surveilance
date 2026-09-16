export interface Sector {
  id: string
  name: string
  enabled: boolean
}

export interface Camera {
  id: string
  name: string
  lat: number | null
  lon: number | null
  source: string
  sector_id: string | null
  enabled: boolean
}

export interface ToolsConfig {
  internet: boolean
  weather: boolean
  maps: boolean
}

export interface AppConfig {
  sectors: Sector[]
  cameras: Camera[]
  tools: ToolsConfig
}

export const UNASSIGNED_SECTOR_ID = 'unassigned'

export function createEmptySector(): Sector {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
  }
}

export function createEmptyCamera(sectorId: string): Camera {
  return {
    id: crypto.randomUUID(),
    name: '',
    lat: null,
    lon: null,
    source: '',
    sector_id: sectorId,
    enabled: true,
  }
}

export function isCameraEffective(sector: Sector, camera: Camera): boolean {
  return sector.enabled && camera.enabled
}

export function camerasInSector(sectorId: string, cameras: Camera[]): Camera[] {
  return cameras.filter((camera) => camera.sector_id === sectorId)
}

export function countEffectiveCameras(sector: Sector, cameras: Camera[]): number {
  return camerasInSector(sector.id, cameras).filter((camera) =>
    isCameraEffective(sector, camera),
  ).length
}

export function canRemoveSector(
  sector: Sector,
  cameras: Camera[],
): { ok: true } | { ok: false; reason: string } {
  if (sector.id === UNASSIGNED_SECTOR_ID) {
    return { ok: false, reason: 'The Unassigned sector cannot be removed.' }
  }
  const assigned = camerasInSector(sector.id, cameras)
  if (assigned.length > 0) {
    return {
      ok: false,
      reason: `Cannot remove sector while ${assigned.length} camera(s) are still assigned.`,
    }
  }
  return { ok: true }
}
