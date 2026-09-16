export type MessageRole = 'user' | 'assistant'

export interface Message {
  role: MessageRole
  content: string
  imageUrls?: string[]
}

export interface Conversation {
  id: string
  messages: Message[]
}
