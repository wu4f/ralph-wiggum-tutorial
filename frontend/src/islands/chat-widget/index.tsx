import { createRoot } from 'react-dom/client'

import { ChatWidget } from './ChatWidget'

export function mount(element: HTMLElement): void {
  element.innerHTML = ''
  createRoot(element).render(<ChatWidget />)
}
