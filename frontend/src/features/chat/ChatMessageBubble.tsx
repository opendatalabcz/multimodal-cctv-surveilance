import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { useState } from 'react'
import type { ImageAnnotation, Message, PresentedImage } from '../../shared/models/conversation'
import { AssistantMarkdown } from './AssistantMarkdown'

interface ChatMessageBubbleProps {
  message: Message
  modelLabel?: string | null
}

const MARK = '#fff4cc'
const HALO = '#111827'

export function ChatMessageBubble({ message, modelLabel }: ChatMessageBubbleProps) {
  const isUser = message.role === 'user'
  const [expandedUrl, setExpandedUrl] = useState<string | null>(null)
  const images = message.images ?? []
  const expanded = images.find((image) => image.url === expandedUrl) ?? null

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
        {!isUser && modelLabel && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            {modelLabel}
          </Typography>
        )}
        {isUser ? (
          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap' }}>
            {message.content}
          </Typography>
        ) : (
          <AssistantMarkdown content={message.content} />
        )}
        {images.length > 0 && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
            {images.map((image) => (
              <Box
                key={image.url}
                component="button"
                type="button"
                onClick={() => setExpandedUrl(image.url)}
                aria-label={
                  image.annotations.length > 0
                    ? 'Expand camera capture with model highlights'
                    : 'Expand camera capture'
                }
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
                <AnnotatedFrame image={image} maxHeight={240} />
              </Box>
            ))}
          </Box>
        )}

        <Dialog
          open={expanded !== null}
          onClose={() => setExpandedUrl(null)}
          maxWidth="lg"
          fullWidth
        >
          <DialogContent sx={{ p: 1, textAlign: 'center' }}>
            {expanded && <AnnotatedFrame image={expanded} maxHeight="80vh" />}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setExpandedUrl(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Paper>
    </Box>
  )
}

function AnnotatedFrame({
  image,
  maxHeight,
}: {
  image: PresentedImage
  maxHeight: number | string
}) {
  return (
    <Box sx={{ position: 'relative', display: 'inline-block', maxWidth: '100%', lineHeight: 0 }}>
      <Box
        component="img"
        src={image.url}
        alt={`Camera ${image.cameraId}`}
        sx={{
          display: 'block',
          maxWidth: '100%',
          maxHeight,
          width: 'auto',
          height: 'auto',
        }}
      />
      {image.annotations.length > 0 && <AnnotationOverlay annotations={image.annotations} />}
    </Box>
  )
}

function AnnotationOverlay({ annotations }: { annotations: ImageAnnotation[] }) {
  return (
    <Box sx={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      <Box
        component="svg"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      >
        {annotations.map((annotation, index) => (
          <Geometry key={`${annotation.type}-${index}`} annotation={annotation} />
        ))}
      </Box>
      {annotations.map((annotation, index) => (
        <PointAndLabel key={`${annotation.type}-mark-${index}`} annotation={annotation} />
      ))}
    </Box>
  )
}

function Geometry({ annotation }: { annotation: ImageAnnotation }) {
  if (annotation.type === 'box' && annotation.points.length === 2) {
    const [first, second] = annotation.points
    const x = Math.min(first[0], second[0])
    const y = Math.min(first[1], second[1])
    const width = Math.abs(second[0] - first[0])
    const height = Math.abs(second[1] - first[1])
    return (
      <>
        <rect x={x} y={y} width={width} height={height} fill="none" {...haloStroke()} />
        <rect x={x} y={y} width={width} height={height} {...markStroke()} />
      </>
    )
  }
  if (annotation.type === 'line' && annotation.points.length >= 2) {
    const points = pointList(annotation.points)
    return (
      <>
        <polyline points={points} fill="none" {...haloStroke()} />
        <polyline points={points} {...markStroke()} />
      </>
    )
  }
  if (annotation.type === 'polygon' && annotation.points.length >= 3) {
    const points = pointList(annotation.points)
    return (
      <>
        <polygon points={points} fill="none" {...haloStroke()} />
        <polygon points={points} {...markStroke()} />
      </>
    )
  }
  return null
}

function PointAndLabel({ annotation }: { annotation: ImageAnnotation }) {
  const anchor = labelAnchor(annotation)
  return (
    <>
      {annotation.type === 'point' && annotation.points[0] && <PointMark point={annotation.points[0]} />}
      {annotation.label && anchor && <HighlightLabel x={anchor[0]} y={anchor[1]} text={annotation.label} />}
    </>
  )
}

function PointMark({ point }: { point: number[] }) {
  return (
    <Box
      sx={{
        position: 'absolute',
        left: `${point[0] / 10}%`,
        top: `${point[1] / 10}%`,
        width: 12,
        height: 12,
        marginLeft: '-6px',
        marginTop: '-6px',
        borderRadius: '50%',
        boxSizing: 'border-box',
        border: `2px solid ${MARK}`,
        boxShadow: `0 0 0 2px ${HALO}`,
      }}
    />
  )
}

function HighlightLabel({ x, y, text }: { x: number; y: number; text: string }) {
  const above = y > 80
  return (
    <Box
      component="span"
      sx={{
        position: 'absolute',
        left: `${x / 10}%`,
        top: `${y / 10}%`,
        transform: above ? 'translate(6px, -130%)' : 'translate(6px, 8px)',
        color: MARK,
        fontSize: 12,
        fontWeight: 600,
        lineHeight: 1.2,
        whiteSpace: 'nowrap',
        textShadow: `0 0 2px ${HALO}, 0 0 4px ${HALO}, 1px 1px 0 ${HALO}`,
      }}
    >
      {text}
    </Box>
  )
}

function labelAnchor(annotation: ImageAnnotation): number[] | null {
  if (annotation.points.length === 0) {
    return null
  }
  if (annotation.type === 'box' && annotation.points.length === 2) {
    const [first, second] = annotation.points
    return [Math.min(first[0], second[0]), Math.min(first[1], second[1])]
  }
  return annotation.points[0]
}

function pointList(points: number[][]): string {
  return points.map((point) => `${point[0]},${point[1]}`).join(' ')
}

function haloStroke() {
  return {
    stroke: HALO,
    strokeWidth: 5,
    vectorEffect: 'non-scaling-stroke' as const,
    strokeLinejoin: 'round' as const,
    strokeLinecap: 'round' as const,
  }
}

function markStroke() {
  return {
    fill: 'none',
    stroke: MARK,
    strokeWidth: 2,
    vectorEffect: 'non-scaling-stroke' as const,
    strokeLinejoin: 'round' as const,
    strokeLinecap: 'round' as const,
  }
}
