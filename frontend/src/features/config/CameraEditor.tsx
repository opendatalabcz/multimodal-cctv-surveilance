import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type MouseEvent } from 'react'
import type { Camera, Location, SceneTag } from '../../shared/models/config'
import { SCENE_TAGS, previewUrlForAnalysis } from '../../shared/models/config'
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
  onPreview: () => void
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
  onPreview,
}: CameraEditorProps) {
  const [expanded, setExpanded] = useState(false)
  const previewUrl = previewUrlForAnalysis(camera.analysis)
  const tags = camera.analysis?.scene_tags ?? []
  const isAnalyzing =
    analysisState?.status === 'queued' || analysisState?.status === 'analyzing'

  const updateAnalysis = (description: string, sceneTags: SceneTag[]) => {
    onChange({
      ...camera,
      analysis: {
        description,
        scene_tags: sceneTags.slice(0, 6),
        source_fingerprint: camera.analysis?.source_fingerprint ?? '',
        analyzed_at: camera.analysis?.analyzed_at ?? new Date().toISOString(),
        preview_path: camera.analysis?.preview_path ?? null,
      },
    })
  }

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 1,
        mb: 1,
        opacity: locationEnabled ? 1 : 0.72,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box
          component={previewUrl ? 'button' : 'div'}
          type={previewUrl ? 'button' : undefined}
          onClick={(event: MouseEvent<HTMLElement>) => {
            event.stopPropagation()
            if (previewUrl) {
              onPreview()
            }
          }}
          aria-label={previewUrl ? `Preview ${camera.name.trim() || 'camera'}` : undefined}
          sx={{
            position: 'relative',
            width: 72,
            height: 48,
            flexShrink: 0,
            border: 0,
            p: 0,
            borderRadius: 0.5,
            overflow: 'hidden',
            bgcolor: 'grey.200',
            cursor: previewUrl ? 'zoom-in' : 'default',
          }}
        >
          {previewUrl ? (
            <Box
              component="img"
              src={previewUrl}
              alt=""
              sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
          ) : (
            <Box
              sx={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Typography variant="caption" color="text.secondary">
                —
              </Typography>
            </Box>
          )}
          {isAnalyzing && (
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'rgba(255,255,255,0.7)',
              }}
            >
              <CircularProgress size={18} />
            </Box>
          )}
        </Box>

        <Box
          onClick={() => setExpanded((current) => !current)}
          sx={{ flex: 1, minWidth: 0, cursor: 'pointer' }}
        >
          <Typography variant="subtitle2" noWrap>
            {camera.name.trim() || 'Camera'}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
            {camera.analysis?.description?.trim() || 'Not analyzed'}
          </Typography>
          {tags.length > 0 && (
            <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, overflow: 'hidden' }}>
              {tags.slice(0, 2).map((tag) => (
                <Chip key={tag} size="small" label={tag} variant="outlined" />
              ))}
            </Box>
          )}
          {!locationEnabled && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              Inactive until location is enabled
            </Typography>
          )}
        </Box>

        <Switch
          size="small"
          checked={camera.enabled}
          onChange={(_, checked) => onToggleEnabled(checked)}
          disabled={!locationEnabled}
          slotProps={{ input: { 'aria-label': 'Enable camera' } }}
        />
        <IconButton
          size="small"
          onClick={() => setExpanded((current) => !current)}
          aria-label={expanded ? 'Collapse camera' : 'Expand camera'}
          sx={{
            transform: expanded ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.15s',
          }}
        >
          ▾
        </IconButton>
      </Box>

      {expanded && (
        <Box sx={{ pt: 1, px: 0.5 }}>
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
          <Autocomplete
            multiple
            size="small"
            options={[...SCENE_TAGS]}
            value={tags}
            onChange={(_, value) =>
              updateAnalysis(
                camera.analysis?.description ?? 'Manually classified camera view',
                value,
              )
            }
            renderValue={(value, getItemProps) =>
              value.map((option, index) => {
                const { key, ...chipProps } = getItemProps({ index })
                return <Chip key={key} size="small" label={option} {...chipProps} />
              })
            }
            renderInput={(params) => (
              <TextField {...params} label="Scene tags" margin="dense" />
            )}
          />
          <Button
            size="small"
            variant="outlined"
            onClick={onAnalyze}
            disabled={isAnalyzing || !camera.source.trim()}
            startIcon={isAnalyzing ? <CircularProgress size={14} /> : undefined}
            sx={{ mt: 0.5, mr: 1 }}
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
          <Button size="small" color="error" onClick={onRemove} sx={{ mt: 0.5 }}>
            Remove camera
          </Button>
        </Box>
      )}
    </Box>
  )
}
