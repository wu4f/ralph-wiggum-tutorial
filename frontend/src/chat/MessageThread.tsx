import type { Message } from './types'

/**
 * Renders a list of chat messages. Each assistant message shows its answer
 * text followed by clickable source-page links (when present).
 */
export function MessageThread({ messages }: { messages: Message[] }) {
  return (
    <>
      {messages.map((message, index) => {
        const isUser = message.role === 'user'
        return (
          <div
            key={index}
            aria-label={isUser ? 'user message' : 'assistant message'}
            className={isUser ? 'text-right' : 'text-left'}
          >
            <div
              className={`inline-block max-w-[85%] rounded-2xl px-3 py-2 text-sm ${
                isUser
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {message.sources && message.sources.length > 0 ? (
                <div className="mt-2 border-t border-gray-300 pt-2">
                  <p className="text-xs font-semibold text-gray-600">Sources</p>
                  <ul className="mt-1 space-y-0.5">
                    {message.sources.map((source, sourceIndex) => (
                      <li key={sourceIndex}>
                        <a
                          href={source.url}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          {source.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </div>
        )
      })}
    </>
  )
}
