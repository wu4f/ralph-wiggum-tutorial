export interface Source {
  title: string
  url: string
}

export interface ChatResponse {
  answer: string
  sources: Source[]
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}
