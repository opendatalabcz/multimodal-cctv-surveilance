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
  UNASSIGNED_SECTOR_ID,
  canRemoveSector,
  countEffectiveCameras,
  locationsInSector,
} from '../../shared/models/config'
import { LocationAccordion } from './LocationAccordion'
import type { CameraAnalysisState } from './useConfig'

interface SectorAccordionProps {
  sector: Sector
  locations: Location[]
  cameras: Camera[]
  expanded: boolean
  expandedLocations: Record<string, boolean>
  onExpandedChange: (expanded: boolean) => void
  onLocationExpandedChange: (locationId: string, expanded: boolean) => void
  onSectorChange: (sector: Sector) => void
  onSectorEnabledChange: (enabled: boolean) => void
  onRemoveSector: () => void
  onAddLocation: () => void
  onUpdateLocation: (locationId: string, location: Location) => void
  onRemoveLocation: (locationId: string) => void
  onToggleLocationEnabled: (locationId: string, enabled: boolean) => void
  onAddCamera: (locationId: string) => void
  onUpdateCamera: (cameraId: string, camera: Camera) => void
  onMoveCamera: (cameraId: string, locationId: string, sectorId: string) => void
  onToggleCameraEnabled: (cameraId: string, enabled: boolean) => void
  onRemoveCamera: (cameraId: string) => void
  analysisStates: Record<string, CameraAnalysisState>
  onAnalyzeCamera: (cameraId: string) => void
  onPreviewCamera: (camera: Camera) => void
}

export function SectorAccordion({
  sector,
  locations,
  cameras,
  expanded,
  expandedLocations,
  onExpandedChange,
  onLocationExpandedChange,
  onSectorChange,
  onSectorEnabledChange,
  onRemoveSector,
  onAddLocation,
  onUpdateLocation,
  onRemoveLocation,
  onToggleLocationEnabled,
  onAddCamera,
  onUpdateCamera,
  onMoveCamera,
  onToggleCameraEnabled,
  onRemoveCamera,
  analysisStates,
  onAnalyzeCamera,
  onPreviewCamera,
}: SectorAccordionProps) {
  const sectorLocations = locationsInSector(sector.id, locations)
  const activeCount = countEffectiveCameras(sector, locations, cameras)
  const removal = canRemoveSector(sector, locations, cameras)
  const isDisabled = !sector.enabled

  const isLocationExpanded = (locationId: string) => expandedLocations[locationId] ?? false

  return (
    <Accordion
      expanded={expanded}
      onChange={(_, nextExpanded) => onExpandedChange(nextExpanded)}
      disableGutters
      sx={{
        mb: 1,
        opacity: isDisabled ? 0.72 : 1,
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
                checked={sector.enabled}
                onChange={(_, checked) => onSectorEnabledChange(checked)}
              />
            }
            label=""
            sx={{ mr: 0 }}
          />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle2" noWrap>
              {sector.name.trim() || 'Untitled sector'}
            </Typography>
            {isDisabled && (
              <Typography variant="caption" color="text.secondary">
                Sector disabled
              </Typography>
            )}
          </Box>
          <Chip size="small" label={`${activeCount} active`} variant="outlined" />
          {sector.id !== UNASSIGNED_SECTOR_ID && (
            <Tooltip title={removal.ok ? 'Remove sector' : removal.reason}>
              <span>
                <IconButton
                  size="small"
                  color="error"
                  disabled={!removal.ok}
                  onClick={(event) => {
                    event.stopPropagation()
                    onRemoveSector()
                  }}
                  aria-label="Remove sector"
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
          label="Sector name"
          size="small"
          margin="dense"
          value={sector.name}
          onChange={(event) => onSectorChange({ ...sector, name: event.target.value })}
        />
        {!removal.ok && sector.id !== UNASSIGNED_SECTOR_ID && (
          <Alert severity="info" sx={{ mt: 1, mb: 1 }}>
            {removal.reason}
          </Alert>
        )}
        {sectorLocations.map((location) => (
          <LocationAccordion
            key={location.id}
            location={location}
            sector={sector}
            locations={locations}
            cameras={cameras}
            expanded={isLocationExpanded(location.id)}
            onExpandedChange={(nextExpanded) =>
              onLocationExpandedChange(location.id, nextExpanded)
            }
            onLocationChange={(next) => onUpdateLocation(location.id, next)}
            onLocationEnabledChange={(enabled) => onToggleLocationEnabled(location.id, enabled)}
            onRemoveLocation={() => onRemoveLocation(location.id)}
            onAddCamera={() => onAddCamera(location.id)}
            onUpdateCamera={onUpdateCamera}
            onMoveCamera={onMoveCamera}
            onToggleCameraEnabled={onToggleCameraEnabled}
            onRemoveCamera={onRemoveCamera}
            analysisStates={analysisStates}
            onAnalyzeCamera={onAnalyzeCamera}
            onPreviewCamera={onPreviewCamera}
          />
        ))}
        <Button variant="outlined" fullWidth onClick={onAddLocation} sx={{ mt: 1 }}>
          Add location
        </Button>
      </AccordionDetails>
    </Accordion>
  )
}
