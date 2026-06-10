import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LearningIsland } from '@/islands/learning/LearningIsland'
import type { AnalysisPayload, FlowScoreResult } from '@/learning/types'

const viewStep = {
  id: 'file:src/app/views/home.py',
  label: 'home.py',
  path: 'src/app/views/home.py',
  kind: 'route',
}
const templateStep = {
  id: 'file:src/app/templates/home.html',
  label: 'home.html',
  path: 'src/app/templates/home.html',
  kind: 'template',
}

const analysis: AnalysisPayload = {
  analysisId: 'analysis-1',
  expiresAt: '2026-06-10T00:30:00+00:00',
  repository: {
    owner: 'copilot-fixtures',
    repo: 'demo',
    url: 'https://github.com/copilot-fixtures/demo',
    defaultBranch: 'main',
  },
  summary: {
    languages: ['Python', 'HTML'],
    frameworks: [{ id: 'framework:flask', label: 'Flask' }],
    fileCount: 6,
    flowCount: 1,
  },
  graph: {
    nodes: [viewStep, templateStep],
    edges: [
      {
        id: 'e1',
        sourceId: viewStep.id,
        targetId: templateStep.id,
        label: 'renders',
      },
    ],
  },
  flows: [
    {
      id: 'flow:request:/',
      title: 'Request to /',
      trigger: 'HTTP GET /',
      prompt: 'Click the files in the order they execute.',
      steps: [templateStep, viewStep],
    },
  ],
  flowsAvailable: true,
}

const perfectResult: FlowScoreResult = {
  flowId: 'flow:request:/',
  score: 2,
  maxScore: 2,
  isCorrect: true,
  feedback: 'Correct — that is the execution order for this flow.',
  correctOrder: [viewStep, templateStep],
}

function mockFetch() {
  return vi.spyOn(global, 'fetch').mockImplementation((input) => {
    const url = String(input)
    const body = url.includes('/score') ? perfectResult : analysis
    const status = url.includes('/score') ? 200 : 201
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

describe('LearningIsland', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/')
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('maps a repository and renders the execution-flow quiz', async () => {
    mockFetch()
    render(<LearningIsland />)

    fireEvent.change(screen.getByLabelText(/public github repository url/i), {
      target: { value: analysis.repository.url },
    })
    fireEvent.click(screen.getByRole('button', { name: /map repository/i }))

    expect(await screen.findByText(/request to \//i)).toBeInTheDocument()
    expect(screen.getByLabelText('Repository execution map')).toBeInTheDocument()
    expect(screen.getByText(/click the files in the order they execute/i)).toBeInTheDocument()
  })

  it('scores a flow when the student orders the nodes', async () => {
    mockFetch()
    render(<LearningIsland />)

    fireEvent.change(screen.getByLabelText(/public github repository url/i), {
      target: { value: analysis.repository.url },
    })
    fireEvent.click(screen.getByRole('button', { name: /map repository/i }))

    await screen.findByText(/request to \//i)

    fireEvent.click(screen.getByRole('button', { name: /home\.py \(route\)/i }))
    fireEvent.click(screen.getByRole('button', { name: /home\.html \(template\)/i }))
    fireEvent.click(screen.getByRole('button', { name: /check flow/i }))

    await waitFor(() => {
      expect(screen.getByText(/score 2\/2/i)).toBeInTheDocument()
    })
    expect(
      screen.getByText(/that is the execution order/i),
    ).toBeInTheDocument()
  })
})
