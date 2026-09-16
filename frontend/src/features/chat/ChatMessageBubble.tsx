import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import type { Message } from '../../shared/models/conversation'

interface ChatMessageBubbleProps {
  message: Message
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 1.5,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          maxWidth: '75%',
          px: 2,
          py: 1.5,
          bgcolor: isUser ? 'primary.main' : 'grey.100',
          color: isUser ? 'primary.contrastText' : 'text.primary',
          borderRadius: 2,
        }}
      >
        <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
          {message.content}
        </Typography>
        {message.imageUrls && message.imageUrls.length > 0 && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
            {message.imageUrls.map((url) => (
              <Box
                key={url}
                component="img"
                src={url}
                alt="Camera capture"
                sx={{
                  maxWidth: '100%',
                  maxHeight: 240,
                  borderRadius: 1,
                  objectFit: 'contain',
                }}
              />
            ))}
          </Box>
        )}
      </Paper>
    </Box>
  )
}
