import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import Switch from '@mui/material/Switch'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import type { AppConfig, Camera, Location, Sector } from '../../shared/models/config'
import { UNASSIGNED_SECTOR_ID, locationsInSector } from '../../shared/models/config'
import { SectorAccordion } from './SectorAccordion'

interface ConfigPanelProps {
  config: AppConfig | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  onSave: () => void
  onToggleTool: (key: keyof AppConfig['tools'], value: boolean) => void
  onUpdateCamera: (cameraId: string, camera: Camera) => void
  onAddCamera: (sectorId: string, locationId: string) => void
  onRemoveCamera: (cameraId: string) => void
  onMoveCamera: (cameraId: string, locationId: string, sectorId: string) => void
  onUpdateSector: (sectorId: string, sector: Sector) => void
  onAddSector: () => void
  onRemoveSector: (sectorId: string) => void
  onUpdateLocation: (locationId: string, location: Location) => void
  onAddLocation: (sectorId: string) => void
  onRemoveLocation: (locationId: string) => void
  onToggleSectorEnabled: (sectorId: string, enabled: boolean) => void
  onToggleLocationEnabled: (locationId: string, enabled: boolean) => void
  onToggleCameraEnabled: (cameraId: string, enabled: boolean) => void
}

export function ConfigPanel({
  config,
  isLoading,
  isSaving,
  error,
  onSave,
  onToggleTool,
  onUpdateCamera,
  onAddCamera,
  onRemoveCamera,
  onMoveCamera,
  onUpdateSector,
  onAddSector,
  onRemoveSector,
  onUpdateLocation,
  onAddLocation,
  onRemoveLocation,
  onToggleSectorEnabled,
  onToggleLocationEnabled,
  onToggleCameraEnabled,
}: ConfigPanelProps) {
  const [expandedSectors, setExpandedSectors] = useState<Record<string, boolean>>({})
  const [expandedLocations, setExpandedLocations] = useState<Record<string, boolean>>({})

  const canSave =
    config !== null &&
    config.sectors.every((sector) => sector.name.trim()) &&
    config.locations.every((location) => location.name.trim()) &&
    config.cameras.every((camera) => camera.name.trim() && camera.source.trim())

  const isSectorExpanded = (sectorId: string) => expandedSectors[sectorId] ?? true

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        borderLeft: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Box sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="h6">Configuration</Typography>
      </Box>

      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 2 }}>
        {isLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={28} />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {config && !isLoading && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Sectors, locations & cameras
            </Typography>
            {config.sectors
              .filter(
                (sector) =>
                  sector.id !== UNASSIGNED_SECTOR_ID ||
                  locationsInSector(sector.id, config.locations).length > 0,
              )
              .map((sector) => (
                <SectorAccordion
                  key={sector.id}
                  sector={sector}
                  locations={config.locations}
                  cameras={config.cameras}
                  expanded={isSectorExpanded(sector.id)}
                  expandedLocations={expandedLocations}
                  onExpandedChange={(expanded) =>
                    setExpandedSectors((current) => ({ ...current, [sector.id]: expanded }))
                  }
                  onLocationExpandedChange={(locationId, expanded) =>
                    setExpandedLocations((current) => ({ ...current, [locationId]: expanded }))
                  }
                  onSectorChange={(next) => onUpdateSector(sector.id, next)}
                  onSectorEnabledChange={(enabled) => onToggleSectorEnabled(sector.id, enabled)}
                  onRemoveSector={() => onRemoveSector(sector.id)}
                  onAddLocation={() => onAddLocation(sector.id)}
                  onUpdateLocation={onUpdateLocation}
                  onRemoveLocation={onRemoveLocation}
                  onToggleLocationEnabled={onToggleLocationEnabled}
                  onAddCamera={(locationId) => onAddCamera(sector.id, locationId)}
                  onUpdateCamera={onUpdateCamera}
                  onMoveCamera={onMoveCamera}
                  onToggleCameraEnabled={onToggleCameraEnabled}
                  onRemoveCamera={onRemoveCamera}
                />
              ))}
            <Button variant="outlined" fullWidth onClick={onAddSector} sx={{ mb: 3 }}>
              Add sector
            </Button>

            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Tools
            </Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={config.tools.internet}
                  onChange={(_, checked) => onToggleTool('internet', checked)}
                  disabled={isSaving}
                />
              }
              label="Internet search"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={config.tools.weather}
                  onChange={(_, checked) => onToggleTool('weather', checked)}
                  disabled={isSaving}
                />
              }
              label="Weather"
            />
            <FormControlLabel
              control={
                <Switch
                  checked={config.tools.maps}
                  onChange={(_, checked) => onToggleTool('maps', checked)}
                  disabled={isSaving}
                />
              }
              label="Map access"
            />
          </>
        )}
      </Box>

      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Button
          variant="contained"
          fullWidth
          disabled={!canSave || isSaving || isLoading}
          onClick={onSave}
        >
          {isSaving ? 'Saving…' : 'Save configuration'}
        </Button>
      </Box>
    </Box>
  )
}
