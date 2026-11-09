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
  showAnnotations?: boolean
}

const MARK = '#fff4cc'
const HALO = '#111827'

export function ChatMessageBubble({
  message,
  modelLabel,
  showAnnotations = false,
}: ChatMessageBubbleProps) {
  const isUser = message.role === 'user'
  const [expandedUrl, setExpandedUrl] = useState<string | null>(null)
  const [activeAnnotation, setActiveAnnotation] = useState<number | null>(null)
  const images = (message.images ?? []).map((image) =>
    showAnnotations ? image : { ...image, annotations: [] },
  )
  const expanded = images.find((image) => image.url === expandedUrl) ?? null
  const closeExpanded = () => {
    setExpandedUrl(null)
    setActiveAnnotation(null)
  }

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
          maxWidth: isUser ? '75%' : '90%',
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
                  flex: '1 1 280px',
                  width: 'min(100%, 420px)',
                  minWidth: 'min(280px, 100%)',
                  maxWidth: 480,
                }}
              >
                <AnnotatedFrame image={image} maxHeight={240} thumbnail />
              </Box>
            ))}
          </Box>
        )}

        <Dialog
          open={expanded !== null}
          onClose={closeExpanded}
          maxWidth="lg"
          fullWidth
        >
          <DialogContent
            sx={{
              p: 1,
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              alignItems: 'stretch',
              gap: 1,
            }}
          >
            {expanded && (
              <>
                <Box sx={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
                  <AnnotatedFrame
                    image={expanded}
                    maxHeight="78vh"
                    activeAnnotation={activeAnnotation}
                    onActiveAnnotation={setActiveAnnotation}
                  />
                </Box>
                {expanded.annotations.length > 0 && (
                  <AnnotationLegend
                    annotations={expanded.annotations}
                    activeAnnotation={activeAnnotation}
                    onActiveAnnotation={setActiveAnnotation}
                  />
                )}
              </>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={closeExpanded}>Close</Button>
          </DialogActions>
        </Dialog>
      </Paper>
    </Box>
  )
}

function AnnotatedFrame({
  image,
  maxHeight,
  thumbnail = false,
  activeAnnotation = null,
  onActiveAnnotation,
}: {
  image: PresentedImage
  maxHeight: number | string
  thumbnail?: boolean
  activeAnnotation?: number | null
  onActiveAnnotation?: (index: number | null) => void
}) {
  const [hoveredAnnotation, setHoveredAnnotation] = useState<number | null>(null)
  const active = thumbnail ? hoveredAnnotation : activeAnnotation
  const setActive = thumbnail ? setHoveredAnnotation : onActiveAnnotation

  return (
    <Box
      sx={{
        position: 'relative',
        display: 'inline-block',
        width: thumbnail ? '100%' : 'auto',
        maxWidth: '100%',
        lineHeight: 0,
      }}
    >
      <Box
        component="img"
        src={image.url}
        alt={`Camera ${image.cameraId}`}
        sx={{
          display: 'block',
          maxWidth: '100%',
          maxHeight,
          width: thumbnail ? '100%' : 'auto',
          height: 'auto',
        }}
      />
      {image.annotations.length > 0 && setActive && (
        <AnnotationOverlay
          annotations={image.annotations}
          activeAnnotation={active}
          onActiveAnnotation={setActive}
        />
      )}
    </Box>
  )
}

function AnnotationOverlay({
  annotations,
  activeAnnotation,
  onActiveAnnotation,
}: {
  annotations: ImageAnnotation[]
  activeAnnotation: number | null
  onActiveAnnotation: (index: number | null) => void
}) {
  const paintOrder = annotations.map((_, index) => index)
  if (activeAnnotation !== null) {
    const activeIndex = paintOrder.indexOf(activeAnnotation)
    if (activeIndex !== -1) {
      paintOrder.splice(activeIndex, 1)
      paintOrder.push(activeAnnotation)
    }
  }

  return (
    <Box sx={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
      <Box
        component="svg"
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        sx={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      >
        {annotations.map((annotation, index) => (
          <HitTarget
            key={`hit-${annotation.type}-${index}`}
            annotation={annotation}
            onMouseEnter={() => onActiveAnnotation(index)}
            onMouseLeave={() => onActiveAnnotation(null)}
          />
        ))}
        {paintOrder.map((index) => (
          <Geometry
            key={`mark-${annotations[index].type}-${index}`}
            annotation={annotations[index]}
            active={activeAnnotation === index}
          />
        ))}
      </Box>
    </Box>
  )
}

function HitTarget({
  annotation,
  onMouseEnter,
  onMouseLeave,
}: {
  annotation: ImageAnnotation
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  const box = hitBounds(annotation.points)
  if (!box) {
    return null
  }
  return (
    <rect
      x={box.x}
      y={box.y}
      width={box.width}
      height={box.height}
      fill="transparent"
      stroke="none"
      pointerEvents="fill"
      cursor="pointer"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    />
  )
}

function Geometry({ annotation, active }: { annotation: ImageAnnotation; active: boolean }) {
  if (annotation.type === 'box' && annotation.points.length === 2) {
    const [first, second] = annotation.points
    const x = Math.min(first[0], second[0])
    const y = Math.min(first[1], second[1])
    const width = Math.abs(second[0] - first[0])
    const height = Math.abs(second[1] - first[1])
    return (
      <g pointerEvents="none">
        <rect x={x} y={y} width={width} height={height} {...haloStroke(active)} />
        <rect x={x} y={y} width={width} height={height} {...markStroke(active)} />
      </g>
    )
  }
  if (annotation.type === 'line' && annotation.points.length >= 2) {
    const points = pointList(annotation.points)
    return (
      <g pointerEvents="none">
        <polyline points={points} {...haloStroke(active)} />
        <polyline points={points} {...markStroke(active)} />
      </g>
    )
  }
  if (annotation.type === 'polygon' && annotation.points.length >= 3) {
    const points = pointList(annotation.points)
    return (
      <g pointerEvents="none">
        <polygon points={points} {...haloStroke(active)} />
        <polygon points={points} {...markStroke(active)} />
      </g>
    )
  }
  if (annotation.type === 'point' && annotation.points[0]) {
    const [x, y] = annotation.points[0]
    return (
      <g pointerEvents="none">
        <circle cx={x} cy={y} r={8} {...haloStroke(active)} />
        <circle cx={x} cy={y} r={6} {...markStroke(active)} />
      </g>
    )
  }
  return null
}

function AnnotationLegend({
  annotations,
  activeAnnotation,
  onActiveAnnotation,
}: {
  annotations: ImageAnnotation[]
  activeAnnotation: number | null
  onActiveAnnotation: (index: number | null) => void
}) {
  return (
    <Box
      aria-label="Image annotations"
      sx={{
        width: { xs: '100%', md: 260 },
        maxHeight: { xs: 220, md: '78vh' },
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.5,
      }}
    >
      {annotations.map((annotation, index) => (
        <Box
          key={`${annotation.type}-legend-${index}`}
          component="button"
          type="button"
          onMouseEnter={() => onActiveAnnotation(index)}
          onMouseLeave={() => onActiveAnnotation(null)}
          onFocus={() => onActiveAnnotation(index)}
          onBlur={() => onActiveAnnotation(null)}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            width: '100%',
            p: 1,
            border: 0,
            borderRadius: 1,
            textAlign: 'left',
            bgcolor: activeAnnotation === index ? 'action.selected' : 'transparent',
            color: 'text.primary',
            cursor: 'pointer',
          }}
        >
          <Box
            component="span"
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 24,
              height: 24,
              flexShrink: 0,
              borderRadius: '50%',
              bgcolor: HALO,
              color: MARK,
              fontSize: 12,
              fontWeight: 700,
            }}
          >
            {index + 1}
          </Box>
          <Box component="span" sx={{ lineHeight: 1.25 }}>
            {annotation.label || `${annotation.type} ${index + 1}`}
          </Box>
        </Box>
      ))}
    </Box>
  )
}

function pointList(points: number[][]): string {
  return points.map((point) => `${point[0]},${point[1]}`).join(' ')
}

function hitBounds(points: number[][]): { x: number; y: number; width: number; height: number } | null {
  if (points.length === 0) {
    return null
  }
  let minX = points[0][0]
  let minY = points[0][1]
  let maxX = minX
  let maxY = minY
  for (const [x, y] of points) {
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
  }
  let x = minX
  let y = minY
  let width = maxX - minX
  let height = maxY - minY
  if (width === 0) {
    x -= 8
    width = 16
  }
  if (height === 0) {
    y -= 8
    height = 16
  }
  return { x, y, width, height }
}

function haloStroke(active: boolean) {
  return {
    stroke: HALO,
    strokeWidth: active ? 7 : 2,
    fill: 'none',
    pointerEvents: 'none' as const,
    vectorEffect: 'non-scaling-stroke' as const,
    strokeLinejoin: 'round' as const,
    strokeLinecap: 'round' as const,
  }
}

function markStroke(active: boolean) {
  return {
    fill: 'none',
    stroke: MARK,
    strokeWidth: active ? 3 : 1,
    pointerEvents: 'none' as const,
    vectorEffect: 'non-scaling-stroke' as const,
    strokeLinejoin: 'round' as const,
    strokeLinecap: 'round' as const,
  }
}
