import type { ChatResponse, Message } from './types'

/**
 * Ask the chat API a question, sending prior history so the model has
 * conversational memory (multi-turn).
 */
export async function askQuestion(
  question: string,
  history: Message[],
): Promise<ChatResponse> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      history: history.map((m) => ({ role: m.role, content: m.content })),
    }),
  })
  if (!res.ok) throw new Error(`Chat error: ${res.status}`)
  return res.json() as Promise<ChatResponse>
}
