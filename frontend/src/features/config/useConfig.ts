import { useCallback, useState } from 'react'
import { getConfig, putConfig } from '../../shared/api/configApi'
import type { AppConfig, Camera, Location, Sector } from '../../shared/models/config'
import {
  createEmptyCamera,
  createEmptyLocation,
  createEmptySector,
} from '../../shared/models/config'

interface UseConfigResult {
  config: AppConfig | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  loadConfig: () => Promise<void>
  saveConfig: (next: AppConfig) => Promise<void>
  updateCamera: (cameraId: string, camera: Camera) => void
  addCamera: (sectorId: string, locationId: string) => void
  removeCamera: (cameraId: string) => void
  moveCamera: (cameraId: string, locationId: string, sectorId: string) => void
  updateSector: (sectorId: string, sector: Sector) => void
  addSector: () => void
  removeSector: (sectorId: string) => void
  updateLocation: (locationId: string, location: Location) => void
  addLocation: (sectorId: string) => void
  removeLocation: (locationId: string) => void
  setSectorEnabled: (sectorId: string, enabled: boolean) => Promise<void>
  setLocationEnabled: (locationId: string, enabled: boolean) => Promise<void>
  setCameraEnabled: (cameraId: string, enabled: boolean) => Promise<void>
  setToolFlag: (key: keyof AppConfig['tools'], value: boolean) => void
}

function updateById<T extends { id: string }>(items: T[], id: string, next: T): T[] {
  return items.map((item) => (item.id === id ? next : item))
}

function applyEnabledFlags(current: AppConfig, saved: AppConfig): AppConfig {
  const sectorEnabled = new Map(saved.sectors.map((sector) => [sector.id, sector.enabled]))
  const locationEnabled = new Map(saved.locations.map((location) => [location.id, location.enabled]))
  const cameraEnabled = new Map(saved.cameras.map((camera) => [camera.id, camera.enabled]))
  return {
    ...current,
    sectors: current.sectors.map((sector) =>
      sectorEnabled.has(sector.id) ? { ...sector, enabled: sectorEnabled.get(sector.id)! } : sector,
    ),
    locations: current.locations.map((location) =>
      locationEnabled.has(location.id)
        ? { ...location, enabled: locationEnabled.get(location.id)! }
        : location,
    ),
    cameras: current.cameras.map((camera) =>
      cameraEnabled.has(camera.id) ? { ...camera, enabled: cameraEnabled.get(camera.id)! } : camera,
    ),
    tools: saved.tools,
  }
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [savedConfig, setSavedConfig] = useState<AppConfig | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const loaded = await getConfig()
      setConfig(loaded)
      setSavedConfig(loaded)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load config'
      setError(message)
      throw err instanceof Error ? err : new Error(message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const saveConfig = useCallback(async (next: AppConfig) => {
    setIsSaving(true)
    setError(null)
    try {
      const saved = await putConfig(next)
      setConfig(saved)
      setSavedConfig(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config')
      throw err
    } finally {
      setIsSaving(false)
    }
  }, [])

  const updateCamera = useCallback((cameraId: string, camera: Camera) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: updateById(current.cameras, cameraId, camera),
      }
    })
  }, [])

  const addCamera = useCallback((sectorId: string, locationId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: [...current.cameras, createEmptyCamera(sectorId, locationId)],
      }
    })
  }, [])

  const removeCamera = useCallback((cameraId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: current.cameras.filter((camera) => camera.id !== cameraId),
      }
    })
  }, [])

  const moveCamera = useCallback((cameraId: string, locationId: string, sectorId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: current.cameras.map((camera) =>
          camera.id === cameraId
            ? { ...camera, location_id: locationId, sector_id: sectorId }
            : camera,
        ),
      }
    })
  }, [])

  const updateSector = useCallback((sectorId: string, sector: Sector) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        sectors: updateById(current.sectors, sectorId, sector),
      }
    })
  }, [])

  const addSector = useCallback(() => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        sectors: [...current.sectors, createEmptySector()],
      }
    })
  }, [])

  const removeSector = useCallback((sectorId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        sectors: current.sectors.filter((sector) => sector.id !== sectorId),
      }
    })
  }, [])

  const updateLocation = useCallback((locationId: string, location: Location) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        locations: updateById(current.locations, locationId, location),
      }
    })
  }, [])

  const addLocation = useCallback((sectorId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        locations: [...current.locations, createEmptyLocation(sectorId)],
      }
    })
  }, [])

  const removeLocation = useCallback((locationId: string) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        locations: current.locations.filter((location) => location.id !== locationId),
      }
    })
  }, [])

  const setSectorEnabled = useCallback(
    async (sectorId: string, enabled: boolean) => {
      if (!config) {
        return
      }
      const previous = config
      const nextLocal: AppConfig = {
        ...config,
        sectors: config.sectors.map((sector) =>
          sector.id === sectorId ? { ...sector, enabled } : sector,
        ),
      }
      setConfig(nextLocal)
      if (!savedConfig || !savedConfig.sectors.some((sector) => sector.id === sectorId)) {
        return
      }
      const payload: AppConfig = {
        ...savedConfig,
        sectors: savedConfig.sectors.map((sector) =>
          sector.id === sectorId ? { ...sector, enabled } : sector,
        ),
      }
      setError(null)
      try {
        const saved = await putConfig(payload)
        setSavedConfig(saved)
        setConfig((current) => (current ? applyEnabledFlags(current, saved) : saved))
      } catch (err) {
        setConfig(previous)
        const message = err instanceof Error ? err.message : 'Failed to save config'
        setError(message)
        throw err instanceof Error ? err : new Error(message)
      }
    },
    [config, savedConfig],
  )

  const setLocationEnabled = useCallback(
    async (locationId: string, enabled: boolean) => {
      if (!config) {
        return
      }
      const previous = config
      const nextLocal: AppConfig = {
        ...config,
        locations: config.locations.map((location) =>
          location.id === locationId ? { ...location, enabled } : location,
        ),
      }
      setConfig(nextLocal)
      if (!savedConfig || !savedConfig.locations.some((location) => location.id === locationId)) {
        return
      }
      const payload: AppConfig = {
        ...savedConfig,
        locations: savedConfig.locations.map((location) =>
          location.id === locationId ? { ...location, enabled } : location,
        ),
      }
      setError(null)
      try {
        const saved = await putConfig(payload)
        setSavedConfig(saved)
        setConfig((current) => (current ? applyEnabledFlags(current, saved) : saved))
      } catch (err) {
        setConfig(previous)
        const message = err instanceof Error ? err.message : 'Failed to save config'
        setError(message)
        throw err instanceof Error ? err : new Error(message)
      }
    },
    [config, savedConfig],
  )

  const setCameraEnabled = useCallback(
    async (cameraId: string, enabled: boolean) => {
      if (!config) {
        return
      }
      const previous = config
      const nextLocal: AppConfig = {
        ...config,
        cameras: config.cameras.map((camera) =>
          camera.id === cameraId ? { ...camera, enabled } : camera,
        ),
      }
      setConfig(nextLocal)
      if (!savedConfig || !savedConfig.cameras.some((camera) => camera.id === cameraId)) {
        return
      }
      const payload: AppConfig = {
        ...savedConfig,
        cameras: savedConfig.cameras.map((camera) =>
          camera.id === cameraId ? { ...camera, enabled } : camera,
        ),
      }
      setError(null)
      try {
        const saved = await putConfig(payload)
        setSavedConfig(saved)
        setConfig((current) => (current ? applyEnabledFlags(current, saved) : saved))
      } catch (err) {
        setConfig(previous)
        const message = err instanceof Error ? err.message : 'Failed to save config'
        setError(message)
        throw err instanceof Error ? err : new Error(message)
      }
    },
    [config, savedConfig],
  )

  const setToolFlag = useCallback((key: keyof AppConfig['tools'], value: boolean) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        tools: { ...current.tools, [key]: value },
      }
    })
  }, [])

  return {
    config,
    isLoading,
    isSaving,
    error,
    loadConfig,
    saveConfig,
    updateCamera,
    addCamera,
    removeCamera,
    moveCamera,
    updateSector,
    addSector,
    removeSector,
    updateLocation,
    addLocation,
    removeLocation,
    setSectorEnabled,
    setLocationEnabled,
    setCameraEnabled,
    setToolFlag,
  }
}
