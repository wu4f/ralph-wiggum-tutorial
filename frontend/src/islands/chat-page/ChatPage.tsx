import type { FormEvent } from 'react'
import { useState } from 'react'

import { MessageThread } from '@/chat/MessageThread'
import { useChat } from '@/chat/useChat'

/**
 * Full-screen chat experience for the dedicated /chat page. Messages fill the
 * available space and scroll; the input is pinned to the bottom.
 */
export function ChatPage() {
  const { messages, isLoading, send } = useChat()
  const [input, setInput] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const question = input
    setInput('')
    void send(question)
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-4 py-6">
      <div className="flex-1 space-y-4 overflow-y-auto">
        {messages.length === 0 ? (
          <p className="mt-10 text-center text-gray-500">
            Ask me anything about this site…
          </p>
        ) : (
          <MessageThread messages={messages} />
        )}
        {isLoading ? (
          <p aria-label="loading" className="text-gray-400">
            Thinking…
          </p>
        ) : null}
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type a question…"
          aria-label="chat input"
          className="flex-1 rounded-full border px-4 py-3 outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={isLoading || input.trim().length === 0}
          className="rounded-full bg-indigo-600 px-6 py-3 font-semibold text-white hover:bg-indigo-500 disabled:bg-gray-300"
        >
          Send
        </button>
      </form>
    </div>
  )
}
