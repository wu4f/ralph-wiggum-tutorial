import type { FormEvent } from 'react'
import { useState } from 'react'

import { MessageThread } from '@/chat/MessageThread'
import { useChat } from '@/chat/useChat'

/**
 * Floating chat bubble (bottom-right). Collapsed it shows an icon; expanded it
 * opens a panel with the message thread and an input box.
 */
export function ChatWidget() {
  const { messages, isLoading, send } = useChat()
  const [isOpen, setIsOpen] = useState(false)
  const [input, setInput] = useState('')

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const question = input
    setInput('')
    void send(question)
  }

  if (!isOpen) {
    return (
      <button
        type="button"
        aria-label="Open chat"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 h-14 w-14 rounded-full bg-indigo-600 text-2xl text-white shadow-lg hover:bg-indigo-500"
      >
        💬
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[32rem] w-96 max-w-[calc(100vw-3rem)] flex-col rounded-2xl border bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <span className="font-semibold text-gray-900">Ask about this site</span>
        <button
          type="button"
          aria-label="Close chat"
          onClick={() => setIsOpen(false)}
          className="text-gray-500 hover:text-gray-800"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <p className="text-sm text-gray-500">
            Ask me anything about this site…
          </p>
        ) : (
          <MessageThread messages={messages} />
        )}
        {isLoading ? (
          <p aria-label="loading" className="text-sm text-gray-400">
            Thinking…
          </p>
        ) : null}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t p-3">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type a question…"
          aria-label="chat input"
          className="flex-1 rounded-full border px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={isLoading || input.trim().length === 0}
          className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:bg-gray-300"
        >
          Send
        </button>
      </form>
    </div>
  )
}
