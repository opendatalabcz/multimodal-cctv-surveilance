export interface Camera {
  id: string
  name: string
  lat: number | null
  lon: number | null
  source: string
}

export interface ToolsConfig {
  internet: boolean
  weather: boolean
  maps: boolean
}

export interface AppConfig {
  cameras: Camera[]
  tools: ToolsConfig
}

export function createEmptyCamera(): Camera {
  return {
    id: crypto.randomUUID(),
    name: '',
    lat: null,
    lon: null,
    source: '',
  }
}
