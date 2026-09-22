import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import type { Message } from '../../shared/models/conversation'
import { AssistantMarkdown } from './AssistantMarkdown'

interface ChatMessageBubbleProps {
  message: Message
}

export function ChatMessageBubble({ message }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user'
  const [expandedUrl, setExpandedUrl] = useState<string | null>(null)

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
        {isUser ? (
          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
            {message.content}
          </Typography>
        ) : (
          <AssistantMarkdown content={message.content} />
        )}
        {message.imageUrls && message.imageUrls.length > 0 && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
            {message.imageUrls.map((url) => (
              <Box
                key={url}
                component="button"
                type="button"
                onClick={() => setExpandedUrl(url)}
                aria-label="Expand camera capture"
                sx={{
                  p: 0,
                  border: 0,
                  bgcolor: 'transparent',
                  borderRadius: 1,
                  overflow: 'hidden',
                  lineHeight: 0,
                  cursor: 'zoom-in',
                  maxWidth: '100%',
                }}
              >
                <Box
                  component="img"
                  src={url}
                  alt="Camera capture"
                  sx={{
                    maxWidth: '100%',
                    maxHeight: 240,
                    borderRadius: 1,
                    objectFit: 'contain',
                    display: 'block',
                  }}
                />
              </Box>
            ))}
          </Box>
        )}

        <Dialog
          open={expandedUrl !== null}
          onClose={() => setExpandedUrl(null)}
          maxWidth="lg"
          fullWidth
        >
          <DialogContent sx={{ p: 1 }}>
            {expandedUrl && (
              <Box
                component="img"
                src={expandedUrl}
                alt="Camera capture"
                sx={{
                  width: '100%',
                  maxHeight: '80vh',
                  objectFit: 'contain',
                  borderRadius: 1,
                  display: 'block',
                }}
              />
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setExpandedUrl(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Paper>
    </Box>
  )
}
