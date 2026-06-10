import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import { ChatWidget } from '../../src/islands/chat-widget/ChatWidget'

vi.mock('../../src/chat/api', () => ({
  askQuestion: vi.fn().mockResolvedValue({
    answer: 'This site is about widgets.',
    sources: [{ title: 'Home', url: 'http://localhost/home' }],
  }),
}))

describe('ChatWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens, sends a question, and renders the answer with a source link', async () => {
    render(<ChatWidget />)

    fireEvent.click(screen.getByRole('button', { name: /open chat/i }))

    const input = screen.getByLabelText('chat input')
    fireEvent.change(input, { target: { value: 'What is this site?' } })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    expect(await screen.findByText('What is this site?')).toBeInTheDocument()
    expect(
      await screen.findByText('This site is about widgets.'),
    ).toBeInTheDocument()

    await waitFor(() => {
      const link = screen.getByRole('link', { name: 'Home' })
      expect(link).toHaveAttribute('href', 'http://localhost/home')
    })
  })
})
