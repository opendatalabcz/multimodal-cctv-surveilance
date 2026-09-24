import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Typography from '@mui/material/Typography'
import { useEffect, useRef } from 'react'
import { ChatComposer } from './ChatComposer'
import { ChatMessageBubble } from './ChatMessageBubble'
import { ThinkingBubble } from './ThinkingBubble'
import type { Message } from '../../shared/models/conversation'

interface ChatPanelProps {
  messages: Message[]
  suggestions: string[]
  isSending: boolean
  progressDetail?: string | null
  error: string | null
  ready: boolean
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
          justifyContent: 'space-between',
          gap: 1,
        }}
      >
        <Typography variant="h6">CCTV Agent</Typography>
        {onNewChat && (
          <Button size="small" variant="outlined" onClick={onNewChat} disabled={isSending}>
            New chat
          </Button>
        )}
      </Box>

      <Box ref={scrollRef} sx={{ flex: 1, overflow: 'auto', px: 2, py: 2 }}>
        {!ready && (
          <Typography variant="body2" color="text.secondary">
            Starting conversation…
          </Typography>
        )}
        {messages.map((message, index) => (
          <ChatMessageBubble key={`${message.role}-${index}`} message={message} />
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
