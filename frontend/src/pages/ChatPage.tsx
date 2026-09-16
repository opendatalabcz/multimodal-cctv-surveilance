import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { useCallback, useEffect, useState } from 'react'
import { ChatPanel } from '../features/chat/ChatPanel'
import { useChat } from '../features/chat/useChat'
import { ConfigPanel } from '../features/config/ConfigPanel'
import { useConfig } from '../features/config/useConfig'
import type { AppConfig } from '../shared/models/config'

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1565c0',
    },
  },
})

export function ChatPage() {
  const [bootError, setBootError] = useState<string | null>(null)
  const [isBooting, setIsBooting] = useState(true)

  const {
    config,
    isLoading: configLoading,
    isSaving,
    error: configError,
    loadConfig,
    saveConfig,
    updateCamera,
    addCamera,
    removeCamera,
    moveCamera,
    updateSector,
    addSector,
    removeSector,
    updateLocation,
    addLocation,
    removeLocation,
    setSectorEnabled,
    setLocationEnabled,
    setCameraEnabled,
  } = useConfig()

  const {
    messages,
    isSending,
    error: chatError,
    initConversation,
    sendMessage,
    conversationId,
  } = useChat()

  useEffect(() => {
    let cancelled = false

    async function boot() {
      setIsBooting(true)
      setBootError(null)
      try {
        await loadConfig()
        await initConversation()
      } catch (err) {
        if (!cancelled) {
          setBootError(err instanceof Error ? err.message : 'Failed to initialize app')
        }
      } finally {
        if (!cancelled) {
          setIsBooting(false)
        }
      }
    }

    void boot()

    return () => {
      cancelled = true
    }
  }, [loadConfig, initConversation])

  const handleSaveConfig = useCallback(async () => {
    if (!config) {
      return
    }
    await saveConfig(config)
  }, [config, saveConfig])

  const handleToggleTool = useCallback(
    async (key: keyof AppConfig['tools'], value: boolean) => {
      if (!config) {
        return
      }
      const next: AppConfig = {
        ...config,
        tools: { ...config.tools, [key]: value },
      }
      try {
        await saveConfig(next)
      } catch {
        await loadConfig()
      }
    },
    [config, saveConfig, loadConfig],
  )

  const handleToggleSectorEnabled = useCallback(
    async (sectorId: string, enabled: boolean) => {
      try {
        await setSectorEnabled(sectorId, enabled)
      } catch {
        await loadConfig()
      }
    },
    [setSectorEnabled, loadConfig],
  )

  const handleToggleLocationEnabled = useCallback(
    async (locationId: string, enabled: boolean) => {
      try {
        await setLocationEnabled(locationId, enabled)
      } catch {
        await loadConfig()
      }
    },
    [setLocationEnabled, loadConfig],
  )

  const handleToggleCameraEnabled = useCallback(
    async (cameraId: string, enabled: boolean) => {
      try {
        await setCameraEnabled(cameraId, enabled)
      } catch {
        await loadConfig()
      }
    },
    [setCameraEnabled, loadConfig],
  )

  if (isBooting) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Box
          sx={{
            height: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'column',
            gap: 2,
          }}
        >
          <CircularProgress />
          <Box component="span" sx={{ color: 'text.secondary' }}>
            Loading…
          </Box>
        </Box>
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
        {bootError && (
          <Alert severity="error" sx={{ borderRadius: 0 }}>
            {bootError}
          </Alert>
        )}
        <Box sx={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <ChatPanel
              messages={messages}
              isSending={isSending}
              error={chatError}
              ready={conversationId !== null && !bootError}
              onSend={sendMessage}
            />
          </Box>
          <Box sx={{ width: 380, flexShrink: 0 }}>
            <ConfigPanel
              config={config}
              isLoading={configLoading}
              isSaving={isSaving}
              error={configError}
              onSave={handleSaveConfig}
              onToggleTool={handleToggleTool}
              onUpdateCamera={updateCamera}
              onAddCamera={addCamera}
              onRemoveCamera={removeCamera}
              onMoveCamera={moveCamera}
              onUpdateSector={updateSector}
              onAddSector={addSector}
              onRemoveSector={removeSector}
              onUpdateLocation={updateLocation}
              onAddLocation={addLocation}
              onRemoveLocation={removeLocation}
              onToggleSectorEnabled={handleToggleSectorEnabled}
              onToggleLocationEnabled={handleToggleLocationEnabled}
              onToggleCameraEnabled={handleToggleCameraEnabled}
            />
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  )
}
