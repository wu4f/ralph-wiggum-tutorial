import type { AnalysisPayload, FlowScoreResult } from './types'

async function parseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as
    | { message?: string }
    | null
  return payload?.message ?? 'Something went wrong while talking to the learning API.'
}

export async function createAnalysis(repositoryUrl: string): Promise<AnalysisPayload> {
  const response = await fetch('/api/learning/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ repositoryUrl }),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as AnalysisPayload
}

export async function getAnalysis(analysisId: string): Promise<AnalysisPayload> {
  const response = await fetch(`/api/learning/analyses/${analysisId}`, {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as AnalysisPayload
}

export async function scoreFlow(
  analysisId: string,
  flowId: string,
  orderedStepIds: string[],
): Promise<FlowScoreResult> {
  const response = await fetch(`/api/learning/analyses/${analysisId}/score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ flowId, orderedStepIds }),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return (await response.json()) as FlowScoreResult
}
