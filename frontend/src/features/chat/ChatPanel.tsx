import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Typography from '@mui/material/Typography'
import { useEffect, useRef } from 'react'
import { ChatComposer } from './ChatComposer'
import { ChatMessageBubble } from './ChatMessageBubble'
import { ThinkingBubble } from './ThinkingBubble'
import type { Message } from '../../shared/models/conversation'

interface ChatPanelProps {
  messages: Message[]
  isSending: boolean
  error: string | null
  ready: boolean
  onSend: (content: string) => void
  onNewChat?: () => void
}

export function ChatPanel({
  messages,
  isSending,
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
  }, [messages, isSending])

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
        {ready && messages.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Ask a question about the configured cameras.
          </Typography>
        )}
        {messages.map((message, index) => (
          <ChatMessageBubble key={`${message.role}-${index}`} message={message} />
        ))}
        {isSending && <ThinkingBubble />}
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
