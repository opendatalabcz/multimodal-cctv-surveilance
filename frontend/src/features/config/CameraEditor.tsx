import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import type { Camera, Location, SceneTag } from '../../shared/models/config'
import { SCENE_TAGS } from '../../shared/models/config'
import type { CameraAnalysisState } from './useConfig'

interface CameraEditorProps {
  camera: Camera
  locations: Location[]
  locationEnabled: boolean
  onChange: (camera: Camera) => void
  onMove: (locationId: string, sectorId: string) => void
  onToggleEnabled: (enabled: boolean) => void
  onRemove: () => void
  analysisState?: CameraAnalysisState
  onAnalyze: () => void
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
  analysisState,
  onAnalyze,
}: CameraEditorProps) {
  const updateAnalysis = (description: string, sceneTags: SceneTag[]) => {
    onChange({
      ...camera,
      analysis: {
        description,
        scene_tags: sceneTags,
        source_fingerprint: camera.analysis?.source_fingerprint ?? '',
        analyzed_at: camera.analysis?.analyzed_at ?? new Date().toISOString(),
      },
    })
  }
  const isAnalyzing =
    analysisState?.status === 'queued' || analysisState?.status === 'analyzing'

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
      <TextField
        fullWidth
        label="Camera view description"
        size="small"
        margin="dense"
        value={camera.analysis?.description ?? ''}
        onChange={(event) =>
          updateAnalysis(event.target.value, camera.analysis?.scene_tags ?? [])
        }
        helperText={
          analysisState?.status === 'failed'
            ? analysisState.error
            : 'Used to choose relevant cameras before fetching frames'
        }
        error={analysisState?.status === 'failed'}
      />
      <FormControl fullWidth size="small" margin="dense">
        <InputLabel id={`scene-tags-${camera.id}`}>Scene tags</InputLabel>
        <Select
          multiple
          labelId={`scene-tags-${camera.id}`}
          label="Scene tags"
          value={camera.analysis?.scene_tags ?? []}
          onChange={(event) =>
            updateAnalysis(
              camera.analysis?.description ?? 'Manually classified camera view',
              event.target.value as SceneTag[],
            )
          }
        >
          {SCENE_TAGS.map((tag) => (
            <MenuItem key={tag} value={tag}>
              {tag}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <Button
        size="small"
        variant="outlined"
        onClick={onAnalyze}
        disabled={isAnalyzing || !camera.source.trim()}
        startIcon={isAnalyzing ? <CircularProgress size={14} /> : undefined}
        sx={{ mt: 0.5 }}
      >
        {analysisState?.status === 'failed'
          ? 'Retry analysis'
          : camera.analysis
            ? 'Refresh analysis'
            : isAnalyzing
              ? 'Analyzing…'
              : 'Analyze camera'}
      </Button>
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
