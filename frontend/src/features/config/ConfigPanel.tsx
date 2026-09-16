import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import FormControlLabel from '@mui/material/FormControlLabel'
import Switch from '@mui/material/Switch'
import Typography from '@mui/material/Typography'
import type { AppConfig, Camera } from '../../shared/models/config'
import { AddCameraButton, CameraEditor } from './CameraEditor'

interface ConfigPanelProps {
  config: AppConfig | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  onSave: () => void
  onToggleTool: (key: keyof AppConfig['tools'], value: boolean) => void
  onUpdateCamera: (index: number, camera: Camera) => void
  onAddCamera: () => void
  onRemoveCamera: (index: number) => void
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
}: ConfigPanelProps) {
  const canSave =
    config !== null &&
    config.cameras.every((camera) => camera.name.trim() && camera.source.trim())

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
              Cameras
            </Typography>
            {config.cameras.map((camera, index) => (
              <CameraEditor
                key={camera.id}
                camera={camera}
                onChange={(next) => onUpdateCamera(index, next)}
                onRemove={() => onRemoveCamera(index)}
              />
            ))}
            <AddCameraButton onClick={onAddCamera} />

            <Typography variant="subtitle2" sx={{ mt: 3, mb: 1 }}>
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
                  checked={config.tools.google_maps}
                  onChange={(_, checked) => onToggleTool('google_maps', checked)}
                  disabled={isSaving}
                />
              }
              label="Google Maps"
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
