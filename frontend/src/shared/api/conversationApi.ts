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

interface StreamStatusEvent {
  type: 'status'
  stage: string
  detail: string
}

interface StreamDoneEvent {
  type: 'done'
  conversation: Conversation
}

interface StreamErrorEvent {
  type: 'error'
  detail: string
}

type StreamEvent = StreamStatusEvent | StreamDoneEvent | StreamErrorEvent

function parseSseBlocks(buffer: string): { events: string[]; rest: string } {
  const parts = buffer.split('\n\n')
  const rest = parts.pop() ?? ''
  return { events: parts, rest }
}

function dataPayload(block: string): string | null {
  const dataLines = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
  if (!dataLines.length) {
    return null
  }
  return dataLines.join('\n')
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string' && body.detail.length > 0) {
      return body.detail
    }
  } catch {
    // Fall through to status text.
  }
  return response.statusText || 'Chat stream failed'
}

export async function sendMessageStream(
  conversationId: string,
  content: string,
  onStatus: (detail: string) => void,
): Promise<Conversation> {
  const response = await fetch(`/api/conversations/${conversationId}/messages/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    throw new Error(await readErrorDetail(response))
  }
  if (!response.body) {
    throw new Error('Chat stream returned no body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let conversation: Conversation | null = null
  let streamError: string | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseBlocks(buffer)
    buffer = parsed.rest
    for (const block of parsed.events) {
      const payload = dataPayload(block)
      if (!payload) {
        continue
      }
      const event = JSON.parse(payload) as StreamEvent
      if (event.type === 'status') {
        onStatus(event.detail)
      } else if (event.type === 'done') {
        conversation = event.conversation
      } else if (event.type === 'error') {
        streamError = event.detail
      }
    }
  }

  if (streamError) {
    throw new Error(streamError)
  }
  if (!conversation) {
    throw new Error('Chat stream ended without a reply')
  }
  return conversation
}
