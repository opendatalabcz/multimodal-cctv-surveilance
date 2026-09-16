import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import IconButton from '@mui/material/IconButton'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import type { Camera } from '../../shared/models/config'

interface CameraEditorProps {
  camera: Camera
  onChange: (camera: Camera) => void
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

export function CameraEditor({ camera, onChange, onRemove }: CameraEditorProps) {
  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 2,
        mb: 2,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="subtitle2">Camera</Typography>
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
          label="Latitude"
          size="small"
          margin="dense"
          value={camera.lat ?? ''}
          onChange={(event) =>
            onChange({ ...camera, lat: parseOptionalNumber(event.target.value) })
          }
        />
        <TextField
          fullWidth
          label="Longitude"
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
    </Box>
  )
}

interface AddCameraButtonProps {
  onClick: () => void
}

export function AddCameraButton({ onClick }: AddCameraButtonProps) {
  return (
    <Button variant="outlined" fullWidth onClick={onClick}>
      Add camera
    </Button>
  )
}
