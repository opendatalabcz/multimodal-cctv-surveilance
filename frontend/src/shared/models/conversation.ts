export type MessageRole = 'user' | 'assistant'

export interface Message {
  role: MessageRole
  content: string
  imageUrls?: string[]
  model?: string | null
}

export interface Conversation {
  id: string
  messages: Message[]
  suggestions?: string[]
}
