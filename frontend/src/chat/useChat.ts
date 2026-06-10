import { useState } from 'react'

import { askQuestion } from './api'
import type { Message } from './types'

/**
 * Shared chat state + multi-turn send logic, reused by the floating widget and
 * the dedicated chat page so source rendering and history live in one place.
 */
export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)

  async function send(question: string): Promise<void> {
    const trimmed = question.trim()
    if (!trimmed || isLoading) return

    const history = messages
    setMessages((m) => [...m, { role: 'user', content: trimmed }])
    setIsLoading(true)
    try {
      const res = await askQuestion(trimmed, history)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.answer, sources: res.sources },
      ])
    } catch {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: 'Sorry, something went wrong.' },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return { messages, isLoading, send }
}
