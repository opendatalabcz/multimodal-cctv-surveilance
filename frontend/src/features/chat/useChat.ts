import { useCallback, useState } from 'react'
import {
  createConversation,
  sendMessage as sendMessageApi,
} from '../../shared/api/conversationApi'
import type { Message } from '../../shared/models/conversation'

interface UseChatResult {
  conversationId: string | null
  messages: Message[]
  isSending: boolean
  error: string | null
  initConversation: () => Promise<void>
  sendMessage: (content: string) => Promise<void>
}

export function useChat(): UseChatResult {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const initConversation = useCallback(async () => {
    const conversation = await createConversation()
    setConversationId(conversation.id)
    setMessages(conversation.messages)
  }, [])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!conversationId || isSending) {
        return
      }

      const optimisticUserMessage: Message = { role: 'user', content }
      setMessages((current) => [...current, optimisticUserMessage])
      setIsSending(true)
      setError(null)

      try {
        const conversation = await sendMessageApi(conversationId, content)
        setMessages(conversation.messages)
      } catch (err) {
        setMessages((current) => current.filter((message) => message !== optimisticUserMessage))
        setError(err instanceof Error ? err.message : 'Failed to send message')
      } finally {
        setIsSending(false)
      }
    },
    [conversationId, isSending],
  )

  return {
    conversationId,
    messages,
    isSending,
    error,
    initConversation,
    sendMessage,
  }
}
