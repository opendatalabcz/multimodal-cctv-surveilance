import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import FormControl from '@mui/material/FormControl'
import InputLabel from '@mui/material/InputLabel'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import Typography from '@mui/material/Typography'
import { useEffect, useRef } from 'react'
import { ChatComposer } from './ChatComposer'
import { ChatMessageBubble } from './ChatMessageBubble'
import { ThinkingBubble } from './ThinkingBubble'
import type { Message } from '../../shared/models/conversation'
import {
  controlForModel,
  modelLabel,
  reasoningLabel,
  type ModelOption,
  type ModelReasoning,
} from '../../shared/models/config'

function SettingSelect({
  label,
  selectedValue,
  control,
  disabled,
  onSelect,
}: {
  label: string
  selectedValue: string
  control: ModelReasoning | null
  disabled: boolean
  onSelect: (value: string) => void
}) {
  const choices = control?.choices ?? []
  const locked = !control || control.locked || choices.length === 0
  const shown = choices.length > 0 ? choices : [control?.default ?? 'default']
  const value = shown.includes(selectedValue) ? selectedValue : (control?.default ?? shown[0])
  const labelId = `chat-${label.toLowerCase()}-label`

  return (
    <FormControl size="small" sx={{ minWidth: 130 }} disabled={disabled || locked}>
      <InputLabel id={labelId}>{label}</InputLabel>
      <Select
        labelId={labelId}
        label={label}
        value={value}
        onChange={(event) => onSelect(event.target.value)}
      >
        {shown.map((choice) => (
          <MenuItem key={choice} value={choice}>
            {reasoningLabel(choice)}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

interface ChatPanelProps {
  messages: Message[]
  suggestions: string[]
  isSending: boolean
  progressDetail?: string | null
  error: string | null
  ready: boolean
  models: ModelOption[]
  selectedModel: string
  selectedReasoning: string
  selectedVerbosity: string
  onSelectModel: (modelId: string) => void
  onSelectReasoning: (effort: string) => void
  onSelectVerbosity: (level: string) => void
  onSend: (content: string) => void
  onNewChat?: () => void
}

export function ChatPanel({
  messages,
  suggestions,
  isSending,
  progressDetail,
  error,
  ready,
  models,
  selectedModel,
  selectedReasoning,
  selectedVerbosity,
  onSelectModel,
  onSelectReasoning,
  onSelectVerbosity,
  onSend,
  onNewChat,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, isSending, progressDetail])

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      <Box
        sx={{
          px: 2,
          py: 1.5,
          borderBottom: 1,
          borderColor: 'divider',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography variant="h6" noWrap sx={{ flexShrink: 0 }}>
          CCTV Agent
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, ml: 'auto' }}>
          <FormControl size="small" sx={{ minWidth: 160 }} disabled={!ready || isSending || models.length === 0}>
            <InputLabel id="chat-model-label">Model</InputLabel>
            <Select
              labelId="chat-model-label"
              label="Model"
              value={models.some((item) => item.id === selectedModel) ? selectedModel : ''}
              onChange={(event) => onSelectModel(event.target.value)}
            >
              {models.map((item) => (
                <MenuItem key={item.id} value={item.id}>
                  {item.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <SettingSelect
            label="Reasoning"
            selectedValue={selectedReasoning}
            control={controlForModel(selectedModel, models, 'reasoning')}
            disabled={!ready || isSending}
            onSelect={onSelectReasoning}
          />
          <SettingSelect
            label="Verbosity"
            selectedValue={selectedVerbosity}
            control={controlForModel(selectedModel, models, 'verbosity')}
            disabled={!ready || isSending}
            onSelect={onSelectVerbosity}
          />
          {onNewChat && (
            <Button size="small" variant="outlined" onClick={onNewChat} disabled={isSending} sx={{ whiteSpace: 'nowrap' }}>
              New chat
            </Button>
          )}
        </Box>
      </Box>

      <Box ref={scrollRef} sx={{ flex: 1, overflow: 'auto', px: 2, py: 2 }}>
        {!ready && (
          <Typography variant="body2" color="text.secondary">
            Starting conversation…
          </Typography>
        )}
        {messages.map((message, index) => (
          <ChatMessageBubble
            key={`${message.role}-${index}`}
            message={message}
            modelLabel={message.role === 'assistant' ? modelLabel(message.model, models) : null}
          />
        ))}
        {suggestions.length > 0 && !isSending && (
          // These sit in the user's column because they are things the user would say.
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'flex-end',
              gap: 1,
              mb: 1.5,
              pl: '25%',
            }}
          >
            {suggestions.map((suggestion) => (
              <Chip
                key={suggestion}
                label={suggestion}
                variant="outlined"
                color="primary"
                clickable
                disabled={!ready}
                onClick={() => onSend(suggestion)}
              />
            ))}
          </Box>
        )}
        {isSending && <ThinkingBubble detail={progressDetail} />}
        {error && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
      </Box>

      <ChatComposer disabled={!ready || isSending} onSend={onSend} />
    </Box>
  )
}
