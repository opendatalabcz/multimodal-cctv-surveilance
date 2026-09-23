import { useCallback, useState } from 'react'
import {
  createConversation,
  getConversation,
  sendMessage as sendMessageApi,
} from '../../shared/api/conversationApi'
import type { Conversation, Message } from '../../shared/models/conversation'

const CONVERSATION_STORAGE_KEY = 'cctv.conversationId'

let bootInflight: Promise<Conversation> | null = null

function readStoredConversationId(): string | null {
  try {
    return sessionStorage.getItem(CONVERSATION_STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredConversationId(id: string | null): void {
  try {
    if (id) {
      sessionStorage.setItem(CONVERSATION_STORAGE_KEY, id)
    } else {
      sessionStorage.removeItem(CONVERSATION_STORAGE_KEY)
    }
  } catch {
    // Ignore private-mode / disabled storage.
  }
}

async function loadOrCreateConversation(): Promise<Conversation> {
  const storedId = readStoredConversationId()
  if (storedId) {
    try {
      return await getConversation(storedId)
    } catch {
      writeStoredConversationId(null)
    }
  }
  const created = await createConversation()
  writeStoredConversationId(created.id)
  return created
}

interface UseChatResult {
  conversationId: string | null
  messages: Message[]
  isSending: boolean
  error: string | null
  initConversation: () => Promise<void>
  startNewConversation: () => Promise<void>
  sendMessage: (content: string) => Promise<void>
}

export function useChat(): UseChatResult {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const adopt = useCallback((conversation: Conversation) => {
    setConversationId(conversation.id)
    setMessages(conversation.messages)
    writeStoredConversationId(conversation.id)
  }, [])

  const initConversation = useCallback(async () => {
    if (!bootInflight) {
      bootInflight = loadOrCreateConversation()
    }
    adopt(await bootInflight)
  }, [adopt])

  const startNewConversation = useCallback(async () => {
    writeStoredConversationId(null)
    bootInflight = null
    const conversation = await createConversation()
    adopt(conversation)
    setError(null)
  }, [adopt])

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
    startNewConversation,
    sendMessage,
  }
}
