import { createRoot } from 'react-dom/client'

import { LearningIsland } from './LearningIsland'

export function mount(element: HTMLElement, _props: unknown): void {
  element.innerHTML = ''
  createRoot(element).render(<LearningIsland />)
}
