import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import type { Camera, Location, Sector } from '../../shared/models/config'
import {
  UNASSIGNED_LOCATION_ID,
  camerasInLocation,
  canRemoveLocation,
  countEffectiveCamerasInLocation,
} from '../../shared/models/config'
import { CameraEditor } from './CameraEditor'
import type { CameraAnalysisState } from './useConfig'

interface LocationAccordionProps {
  location: Location
  sector: Sector
  locations: Location[]
  cameras: Camera[]
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  onLocationChange: (location: Location) => void
  onLocationEnabledChange: (enabled: boolean) => void
  onRemoveLocation: () => void
  onAddCamera: () => void
  onUpdateCamera: (cameraId: string, camera: Camera) => void
  onMoveCamera: (cameraId: string, locationId: string, sectorId: string) => void
  onToggleCameraEnabled: (cameraId: string, enabled: boolean) => void
  onRemoveCamera: (cameraId: string) => void
  analysisStates: Record<string, CameraAnalysisState>
  onAnalyzeCamera: (cameraId: string) => void
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

export function LocationAccordion({
  location,
  sector,
  locations,
  cameras,
  expanded,
  onExpandedChange,
  onLocationChange,
  onLocationEnabledChange,
  onRemoveLocation,
  onAddCamera,
  onUpdateCamera,
  onMoveCamera,
  onToggleCameraEnabled,
  onRemoveCamera,
  analysisStates,
  onAnalyzeCamera,
}: LocationAccordionProps) {
  const locationCameras = camerasInLocation(location.id, cameras)
  const activeCount = countEffectiveCamerasInLocation(sector, location, cameras)
  const removal = canRemoveLocation(location, cameras)
  const sectorDisabled = !sector.enabled
  const locationDisabled = !location.enabled
  const isMuted = sectorDisabled || locationDisabled
  const isUnassigned =
    location.id === UNASSIGNED_LOCATION_ID || location.id.endsWith('_unassigned')

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, nextExpanded) => onExpandedChange(nextExpanded)}
      disableGutters
      sx={{
        mb: 1,
        opacity: isMuted ? 0.72 : 1,
        border: 1,
        borderColor: 'divider',
        '&::before': { display: 'none' },
      }}
    >
      <AccordionSummary expandIcon={<span aria-hidden>▾</span>}>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            width: '100%',
            pr: 1,
          }}
        >
          <FormControlLabel
            onClick={(event) => event.stopPropagation()}
            onFocus={(event) => event.stopPropagation()}
            control={
              <Switch
                size="small"
                checked={location.enabled}
                onChange={(_, checked) => onLocationEnabledChange(checked)}
                disabled={sectorDisabled}
              />
            }
            label=""
            sx={{ mr: 0 }}
          />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" noWrap>
              {location.name.trim() || 'Untitled location'}
            </Typography>
            {sectorDisabled && (
              <Typography variant="caption" color="text.secondary">
                Inactive until sector is enabled
              </Typography>
            )}
            {!sectorDisabled && locationDisabled && (
              <Typography variant="caption" color="text.secondary">
                Location disabled
              </Typography>
            )}
          </Box>
          <Chip size="small" label={`${activeCount} active`} variant="outlined" />
          {!isUnassigned && (
            <Tooltip title={removal.ok ? 'Remove location' : removal.reason}>
              <span>
                <IconButton
                  size="small"
                  color="error"
                  disabled={!removal.ok}
                  onClick={(event) => {
                    event.stopPropagation()
                    onRemoveLocation()
                  }}
                  aria-label="Remove location"
                >
                  ×
                </IconButton>
              </span>
            </Tooltip>
          )}
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <TextField
          fullWidth
          label="Location name"
          size="small"
          margin="dense"
          value={location.name}
          onChange={(event) => onLocationChange({ ...location, name: event.target.value })}
        />
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField
            fullWidth
            label="Latitude"
            size="small"
            margin="dense"
            value={location.lat ?? ''}
            onChange={(event) =>
              onLocationChange({ ...location, lat: parseOptionalNumber(event.target.value) })
            }
          />
          <TextField
            fullWidth
            label="Longitude"
            size="small"
            margin="dense"
            value={location.lon ?? ''}
            onChange={(event) =>
              onLocationChange({ ...location, lon: parseOptionalNumber(event.target.value) })
            }
          />
        </Box>
        {!removal.ok && !isUnassigned && (
          <Alert severity="info" sx={{ mt: 1, mb: 1 }}>
            {removal.reason}
          </Alert>
        )}
        {locationCameras.map((camera) => (
          <CameraEditor
            key={camera.id}
            camera={camera}
            locations={locations}
            locationEnabled={location.enabled && sector.enabled}
            onChange={(next) => onUpdateCamera(camera.id, next)}
            onMove={(locationId, sectorId) => onMoveCamera(camera.id, locationId, sectorId)}
            onToggleEnabled={(enabled) => onToggleCameraEnabled(camera.id, enabled)}
            onRemove={() => onRemoveCamera(camera.id)}
            analysisState={analysisStates[camera.id]}
            onAnalyze={() => onAnalyzeCamera(camera.id)}
          />
        ))}
        <Button variant="outlined" fullWidth onClick={onAddCamera} sx={{ mt: 1 }}>
          Add camera
        </Button>
      </AccordionDetails>
    </Accordion>
  )
}
