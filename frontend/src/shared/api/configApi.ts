import type { AppConfig, Camera } from '../models/config'
import { apiClient } from './client'

export async function getConfig(): Promise<AppConfig> {
  const response = await apiClient.get<AppConfig>('/config')
  return response.data
}

export async function putConfig(config: AppConfig): Promise<AppConfig> {
  const response = await apiClient.put<AppConfig>('/config', config)
  return response.data
}

export async function analyzeCamera(cameraId: string): Promise<Camera> {
  const response = await apiClient.post<Camera>(`/cameras/${encodeURIComponent(cameraId)}/analyze`)
  return response.data
}
