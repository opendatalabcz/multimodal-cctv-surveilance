export interface Sector {
  id: string
  name: string
  enabled: boolean
}

export interface Location {
  id: string
  name: string
  sector_id: string | null
  enabled: boolean
  lat: number | null
  lon: number | null
}

export const SCENE_TAGS = [
  'road',
  'intersection',
  'highway',
  'parking',
  'bridge',
  'pedestrian',
  'public-square',
  'airport',
  'rail',
  'waterfront',
  'panorama',
  'indoor',
] as const

export type SceneTag = (typeof SCENE_TAGS)[number]

export interface CameraAnalysis {
  description: string
  scene_tags: SceneTag[]
  source_fingerprint: string
  analyzed_at: string
  preview_path?: string | null
}

export function imageUrlForPath(path: string): string {
  const encoded = path.split('/').map(encodeURIComponent).join('/')
  return `/api/images/${encoded}`
}

export function previewUrlForAnalysis(analysis: CameraAnalysis | null | undefined): string | null {
  if (!analysis?.preview_path) {
    return null
  }
  // Re-analysis overwrites the same preview file, so vary the URL to defeat the cached copy.
  return `${imageUrlForPath(analysis.preview_path)}?v=${encodeURIComponent(analysis.analyzed_at)}`
}

export interface Camera {
  id: string
  name: string
  lat: number | null
  lon: number | null
  source: string
  sector_id: string | null
  location_id: string | null
  enabled: boolean
  analysis: CameraAnalysis | null
}

export interface ToolsConfig {
  internet: boolean
  weather: boolean
  maps: boolean
}

export interface AppConfig {
  sectors: Sector[]
  locations: Location[]
  cameras: Camera[]
  tools: ToolsConfig
}

export const UNASSIGNED_SECTOR_ID = 'unassigned'
export const UNASSIGNED_LOCATION_ID = 'unassigned'

export function unassignedLocationId(sectorId: string): string {
  if (sectorId === UNASSIGNED_SECTOR_ID) {
    return UNASSIGNED_LOCATION_ID
  }
  return `${sectorId}_unassigned`
}

export function createEmptySector(): Sector {
  return {
    id: crypto.randomUUID(),
    name: '',
    enabled: true,
  }
}

export function createEmptyLocation(sectorId: string): Location {
  return {
    id: crypto.randomUUID(),
    name: '',
    sector_id: sectorId,
    enabled: true,
    lat: null,
    lon: null,
  }
}

export function createEmptyCamera(sectorId: string, locationId: string): Camera {
  return {
    id: crypto.randomUUID(),
    name: '',
    lat: null,
    lon: null,
    source: '',
    sector_id: sectorId,
    location_id: locationId,
    enabled: true,
    analysis: null,
  }
}

export function isCameraEffective(
  sector: Sector,
  location: Location,
  camera: Camera,
): boolean {
  return sector.enabled && location.enabled && camera.enabled
}

export function locationsInSector(sectorId: string, locations: Location[]): Location[] {
  return locations.filter((location) => location.sector_id === sectorId)
}

export function camerasInLocation(locationId: string, cameras: Camera[]): Camera[] {
  return cameras.filter((camera) => camera.location_id === locationId)
}

export function camerasInSector(sectorId: string, cameras: Camera[]): Camera[] {
  return cameras.filter((camera) => camera.sector_id === sectorId)
}

export function countEffectiveCamerasInLocation(
  sector: Sector,
  location: Location,
  cameras: Camera[],
): number {
  return camerasInLocation(location.id, cameras).filter((camera) =>
    isCameraEffective(sector, location, camera),
  ).length
}

export function countEffectiveCameras(
  sector: Sector,
  locations: Location[],
  cameras: Camera[],
): number {
  return locationsInSector(sector.id, locations).reduce(
    (total, location) => total + countEffectiveCamerasInLocation(sector, location, cameras),
    0,
  )
}

export function canRemoveSector(
  sector: Sector,
  locations: Location[],
  cameras: Camera[],
): { ok: true } | { ok: false; reason: string } {
  if (sector.id === UNASSIGNED_SECTOR_ID) {
    return { ok: false, reason: 'The Unassigned sector cannot be removed.' }
  }
  const assignedLocations = locationsInSector(sector.id, locations)
  if (assignedLocations.length > 0) {
    return {
      ok: false,
      reason: `Cannot remove sector while ${assignedLocations.length} location(s) are still assigned.`,
    }
  }
  const assignedCameras = camerasInSector(sector.id, cameras)
  if (assignedCameras.length > 0) {
    return {
      ok: false,
      reason: `Cannot remove sector while ${assignedCameras.length} camera(s) are still assigned.`,
    }
  }
  return { ok: true }
}

export function canRemoveLocation(
  location: Location,
  cameras: Camera[],
): { ok: true } | { ok: false; reason: string } {
  if (location.id === UNASSIGNED_LOCATION_ID || location.id.endsWith('_unassigned')) {
    return { ok: false, reason: 'The Unassigned location cannot be removed.' }
  }
  const assigned = camerasInLocation(location.id, cameras)
  if (assigned.length > 0) {
    return {
      ok: false,
      reason: `Cannot remove location while ${assigned.length} camera(s) are still assigned.`,
    }
  }
  return { ok: true }
}
