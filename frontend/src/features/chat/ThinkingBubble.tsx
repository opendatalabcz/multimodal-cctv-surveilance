import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'

export function ThinkingBubble() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', mb: 1.5 }}>
      <Paper
        elevation={0}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: 2,
          py: 1.5,
          bgcolor: 'grey.100',
          borderRadius: 2,
        }}
      >
        <CircularProgress size={18} />
        <Typography variant="body2" color="text.secondary">
          Thinking…
        </Typography>
      </Paper>
    </Box>
  )
}
