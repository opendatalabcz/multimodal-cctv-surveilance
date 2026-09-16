import Box from '@mui/material/Box'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import type { Camera, Location } from '../../shared/models/config'

interface CameraEditorProps {
  camera: Camera
  locations: Location[]
  locationEnabled: boolean
  onChange: (camera: Camera) => void
  onMove: (locationId: string, sectorId: string) => void
  onToggleEnabled: (enabled: boolean) => void
  onRemove: () => void
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}

export function CameraEditor({
  camera,
  locations,
  locationEnabled,
  onChange,
  onMove,
  onToggleEnabled,
  onRemove,
}: CameraEditorProps) {
  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 2,
        mb: 1.5,
        opacity: locationEnabled ? 1 : 0.72,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={camera.enabled}
              onChange={(_, checked) => onToggleEnabled(checked)}
              disabled={!locationEnabled}
            />
          }
          label={
            <Box>
              <Typography variant="subtitle2">
                {camera.name.trim() || 'Camera'}
              </Typography>
              {!locationEnabled && (
                <Typography variant="caption" color="text.secondary">
                  Inactive until location is enabled
                </Typography>
              )}
            </Box>
          }
        />
        <IconButton size="small" color="error" onClick={onRemove} aria-label="Remove camera">
          ×
        </IconButton>
      </Box>

      <TextField
        fullWidth
        required
        label="Name"
        size="small"
        margin="dense"
        value={camera.name}
        onChange={(event) => onChange({ ...camera, name: event.target.value })}
      />
      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          fullWidth
          label="Latitude override"
          size="small"
          margin="dense"
          value={camera.lat ?? ''}
          onChange={(event) =>
            onChange({ ...camera, lat: parseOptionalNumber(event.target.value) })
          }
          helperText="Optional; inherits location GPS when empty"
        />
        <TextField
          fullWidth
          label="Longitude override"
          size="small"
          margin="dense"
          value={camera.lon ?? ''}
          onChange={(event) =>
            onChange({ ...camera, lon: parseOptionalNumber(event.target.value) })
          }
        />
      </Box>
      <TextField
        fullWidth
        required
        label="Source URL"
        size="small"
        margin="dense"
        value={camera.source}
        onChange={(event) => onChange({ ...camera, source: event.target.value })}
        helperText="Direct image URL, Prague camera ID, or YouTube live URL"
      />
      <FormControl fullWidth size="small" margin="dense">
        <InputLabel id={`location-select-${camera.id}`}>Location</InputLabel>
        <Select
          labelId={`location-select-${camera.id}`}
          label="Location"
          value={camera.location_id ?? ''}
          onChange={(event) => {
            const locationId = String(event.target.value)
            const location = locations.find((item) => item.id === locationId)
            onMove(locationId, location?.sector_id ?? camera.sector_id ?? '')
          }}
        >
          {locations.map((location) => (
            <MenuItem key={location.id} value={location.id}>
              {location.name.trim() || 'Untitled location'}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Box>
  )
}
