import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import TextField from '@mui/material/TextField'
import { useState, type KeyboardEvent } from 'react'

interface ChatComposerProps {
  disabled: boolean
  onSend: (content: string) => void
}

export function ChatComposer({ disabled, onSend }: ChatComposerProps) {
  const [draft, setDraft] = useState('')

  const handleSend = () => {
    const trimmed = draft.trim()
    if (!trimmed || disabled) {
      return
    }
    onSend(trimmed)
    setDraft('')
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Enter') {
      return
    }
    if (event.shiftKey) {
      return
    }
    if (event.ctrlKey || event.metaKey || !event.shiftKey) {
      event.preventDefault()
      handleSend()
    }
  }

  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', p: 2, borderTop: 1, borderColor: 'divider' }}>
      <TextField
        fullWidth
        multiline
        minRows={1}
        maxRows={6}
        placeholder="Ask about the cameras… (Enter or Ctrl+Enter to send)"
        value={draft}
        disabled={disabled}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
      />
      <Button variant="contained" disabled={disabled || !draft.trim()} onClick={handleSend}>
        Send
      </Button>
    </Box>
  )
}
