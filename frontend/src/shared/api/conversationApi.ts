import type { Conversation } from '../models/conversation'
import { apiClient } from './client'

export async function createConversation(): Promise<Conversation> {
  const response = await apiClient.post<Conversation>('/conversations')
  return response.data
}

export async function getConversation(id: string): Promise<Conversation> {
  const response = await apiClient.get<Conversation>(`/conversations/${id}`)
  return response.data
}

export async function sendMessage(
  conversationId: string,
  content: string,
): Promise<Conversation> {
  const response = await apiClient.post<Conversation>(
    `/conversations/${conversationId}/messages`,
    { content },
  )
  return response.data
}
