import { useCallback, useState } from 'react'
import { getConfig, putConfig } from '../../shared/api/configApi'
import type { AppConfig, Camera } from '../../shared/models/config'
import { createEmptyCamera } from '../../shared/models/config'

interface UseConfigResult {
  config: AppConfig | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  loadConfig: () => Promise<void>
  saveConfig: (next: AppConfig) => Promise<void>
  updateCamera: (index: number, camera: Camera) => void
  addCamera: () => void
  removeCamera: (index: number) => void
  setToolFlag: (key: keyof AppConfig['tools'], value: boolean) => void
}

export function useConfig(): UseConfigResult {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const loaded = await getConfig()
      setConfig(loaded)
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config')
      throw err
    } finally {
      setIsSaving(false)
    }
  }, [])

  const updateCamera = useCallback((index: number, camera: Camera) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      const cameras = [...current.cameras]
      cameras[index] = camera
      return { ...current, cameras }
    })
  }, [])

  const addCamera = useCallback(() => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: [...current.cameras, createEmptyCamera()],
      }
    })
  }, [])

  const removeCamera = useCallback((index: number) => {
    setConfig((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        cameras: current.cameras.filter((_, i) => i !== index),
      }
    })
  }, [])

  const setToolFlag = useCallback(
    (key: keyof AppConfig['tools'], value: boolean) => {
      setConfig((current) => {
        if (!current) {
          return current
        }
        return {
          ...current,
          tools: { ...current.tools, [key]: value },
        }
      })
    },
    [],
  )

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
    setToolFlag,
  }
}
