import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogContentText from '@mui/material/DialogContentText'
import DialogTitle from '@mui/material/DialogTitle'
import FormControlLabel from '@mui/material/FormControlLabel'
import Switch from '@mui/material/Switch'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import type { AppConfig, Camera, Location, Sector } from '../../shared/models/config'
import { UNASSIGNED_SECTOR_ID, imageUrlForPath, locationsInSector } from '../../shared/models/config'
import { SectorAccordion } from './SectorAccordion'
import type { CameraAnalysisState } from './useConfig'

interface ConfigPanelProps {
  config: AppConfig | null
  isLoading: boolean
  isSaving: boolean
  isDirty?: boolean
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
  analysisStates: Record<string, CameraAnalysisState>
  onAnalyzeCamera: (cameraId: string) => void
  onAnalyzeMissing: () => void
  onAnalyzeAll: () => void
}

export function ConfigPanel({
  config,
  isLoading,
  isSaving,
  isDirty = false,
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
  analysisStates,
  onAnalyzeCamera,
  onAnalyzeMissing,
  onAnalyzeAll,
}: ConfigPanelProps) {
  const [expandedSectors, setExpandedSectors] = useState<Record<string, boolean>>({})
  const [expandedLocations, setExpandedLocations] = useState<Record<string, boolean>>({})
  const [previewCamera, setPreviewCamera] = useState<Camera | null>(null)
  const [confirmAnalyzeAll, setConfirmAnalyzeAll] = useState(false)

  const canSave =
    config !== null &&
    config.sectors.every((sector) => sector.name.trim()) &&
    config.locations.every((location) => location.name.trim()) &&
    config.cameras.every((camera) => camera.name.trim() && camera.source.trim())
  const isAnalyzing = Object.values(analysisStates).some(
    (state) => state.status === 'queued' || state.status === 'analyzing',
  )
  const analyzableCount =
    config?.cameras.filter((camera) => camera.source.trim()).length ?? 0
  const canAnalyzeMissing =
    config !== null &&
    !isSaving &&
    !isAnalyzing &&
    config.cameras.some((camera) => !camera.analysis && camera.source.trim())
  const canAnalyzeAll = config !== null && !isSaving && !isAnalyzing && analyzableCount > 0

  const isSectorExpanded = (sectorId: string) => expandedSectors[sectorId] ?? true
  const previewUrl = previewCamera?.analysis?.preview_path
    ? imageUrlForPath(previewCamera.analysis.preview_path)
    : null

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
                  analysisStates={analysisStates}
                  onAnalyzeCamera={onAnalyzeCamera}
                  onPreviewCamera={setPreviewCamera}
                />
              ))}
            <Button variant="outlined" fullWidth onClick={onAddSector} sx={{ mb: 1 }}>
              Add sector
            </Button>
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <Button
                size="small"
                variant="outlined"
                fullWidth
                onClick={onAnalyzeMissing}
                disabled={!canAnalyzeMissing}
              >
                Analyze missing
              </Button>
              <Button
                size="small"
                variant="outlined"
                fullWidth
                onClick={() => setConfirmAnalyzeAll(true)}
                disabled={!canAnalyzeAll}
              >
                Re-analyze all
              </Button>
            </Box>

            <Accordion
              defaultExpanded={false}
              disableGutters
              sx={{
                border: 1,
                borderColor: 'divider',
                '&::before': { display: 'none' },
              }}
            >
              <AccordionSummary expandIcon={<span aria-hidden>▾</span>}>
                <Typography variant="subtitle2">Tools</Typography>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0 }}>
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
              </AccordionDetails>
            </Accordion>
          </>
        )}
      </Box>

      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        {isDirty && (
          <Typography variant="caption" color="warning.main" sx={{ display: 'block', mb: 1 }}>
            {canSave
              ? 'Name and source edits are not saved until you click Save.'
              : 'Fill in every sector, location, and camera name and source before saving.'}
          </Typography>
        )}
        <Button
          variant="contained"
          fullWidth
          color={isDirty ? 'warning' : 'primary'}
          disabled={!canSave || !isDirty || isSaving || isLoading || isAnalyzing}
          onClick={onSave}
        >
          {isSaving ? 'Saving…' : isDirty ? 'Save unsaved changes' : 'Save configuration'}
        </Button>
      </Box>

      <Dialog
        open={confirmAnalyzeAll}
        onClose={() => setConfirmAnalyzeAll(false)}
      >
        <DialogTitle>Re-analyze all cameras?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This fetches a fresh frame and re-runs vision for {analyzableCount}{' '}
            {analyzableCount === 1 ? 'camera' : 'cameras'} with a source, including ones
            that already have metadata. It can take a while and uses Azure credits.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmAnalyzeAll(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => {
              setConfirmAnalyzeAll(false)
              onAnalyzeAll()
            }}
          >
            Re-analyze all
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={previewCamera !== null && previewUrl !== null}
        onClose={() => setPreviewCamera(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{previewCamera?.name.trim() || 'Camera'}</DialogTitle>
        <DialogContent>
          {previewUrl && (
            <Box
              component="img"
              src={previewUrl}
              alt={previewCamera?.name.trim() || 'Camera preview'}
              sx={{ width: '100%', borderRadius: 1, display: 'block' }}
            />
          )}
          {previewCamera?.analysis?.description && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              {previewCamera.analysis.description}
            </Typography>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  )
}
