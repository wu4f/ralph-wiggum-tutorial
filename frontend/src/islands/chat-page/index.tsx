import { createRoot } from 'react-dom/client'

import { ChatPage } from './ChatPage'

export function mount(element: HTMLElement): void {
  element.innerHTML = ''
  createRoot(element).render(<ChatPage />)
}
