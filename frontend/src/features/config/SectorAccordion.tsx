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
import type { Camera, Sector } from '../../shared/models/config'
import {
  UNASSIGNED_SECTOR_ID,
  camerasInSector,
  canRemoveSector,
  countEffectiveCameras,
} from '../../shared/models/config'
import { CameraEditor } from './CameraEditor'

interface SectorAccordionProps {
  sector: Sector
  sectors: Sector[]
  cameras: Camera[]
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  onSectorChange: (sector: Sector) => void
  onSectorEnabledChange: (enabled: boolean) => void
  onRemoveSector: () => void
  onAddCamera: () => void
  onUpdateCamera: (cameraId: string, camera: Camera) => void
  onMoveCamera: (cameraId: string, sectorId: string) => void
  onToggleCameraEnabled: (cameraId: string, enabled: boolean) => void
  onRemoveCamera: (cameraId: string) => void
}

export function SectorAccordion({
  sector,
  sectors,
  cameras,
  expanded,
  onExpandedChange,
  onSectorChange,
  onSectorEnabledChange,
  onRemoveSector,
  onAddCamera,
  onUpdateCamera,
  onMoveCamera,
  onToggleCameraEnabled,
  onRemoveCamera,
}: SectorAccordionProps) {
  const sectorCameras = camerasInSector(sector.id, cameras)
  const activeCount = countEffectiveCameras(sector, cameras)
  const removal = canRemoveSector(sector, cameras)
  const isDisabled = !sector.enabled

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
        {sectorCameras.map((camera) => (
          <CameraEditor
            key={camera.id}
            camera={camera}
            sectors={sectors}
            sectorEnabled={sector.enabled}
            onChange={(next) => onUpdateCamera(camera.id, next)}
            onMove={(sectorId) => onMoveCamera(camera.id, sectorId)}
            onToggleEnabled={(enabled) => onToggleCameraEnabled(camera.id, enabled)}
            onRemove={() => onRemoveCamera(camera.id)}
          />
        ))}
        <Button variant="outlined" fullWidth onClick={onAddCamera} sx={{ mt: 1 }}>
          Add camera
        </Button>
      </AccordionDetails>
    </Accordion>
  )
}
