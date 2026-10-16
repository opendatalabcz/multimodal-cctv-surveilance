type MessageRole = 'user' | 'assistant'

export type AnnotationType = 'box' | 'point' | 'line' | 'polygon'

export interface ImageAnnotation {
  type: AnnotationType
  points: number[][]
  label?: string | null
}

export interface PresentedImage {
  url: string
  cameraId: string
  annotations: ImageAnnotation[]
}

export interface Message {
  role: MessageRole
  content: string
  images?: PresentedImage[]
  model?: string | null
}

export interface Conversation {
  id: string
  messages: Message[]
  suggestions?: string[]
}
