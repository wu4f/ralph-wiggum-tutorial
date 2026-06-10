import type { FormEvent } from 'react'
import { useEffect, useMemo, useState } from 'react'

import { createAnalysis, getAnalysis, scoreFlow } from '@/learning/api'
import { CodeMap } from '@/learning/components/CodeMap'
import type {
  AnalysisPayload,
  CodeGraph,
  Flow,
  FlowScoreResult,
} from '@/learning/types'

type OrderMap = Record<string, string[]>
type ResultMap = Record<string, FlowScoreResult | undefined>

function toggleOrder(order: string[], nodeId: string): string[] {
  return order.includes(nodeId)
    ? order.filter((id) => id !== nodeId)
    : [...order, nodeId]
}

function subGraphForFlow(graph: CodeGraph, flow: Flow): CodeGraph {
  const stepIds = new Set(flow.steps.map((step) => step.id))
  return {
    nodes: graph.nodes.filter((node) => stepIds.has(node.id)),
    edges: graph.edges.filter(
      (edge) => stepIds.has(edge.sourceId) && stepIds.has(edge.targetId),
    ),
  }
}

export function LearningIsland() {
  const [repositoryUrl, setRepositoryUrl] = useState('')
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null)
  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(null)
  const [orders, setOrders] = useState<OrderMap>({})
  const [results, setResults] = useState<ResultMap>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const analysisId = new URLSearchParams(window.location.search).get('analysis_id')
    if (!analysisId) return

    setLoading(true)
    void getAnalysis(analysisId)
      .then((payload) => applyAnalysis(payload))
      .catch((apiError: Error) => setError(apiError.message))
      .finally(() => setLoading(false))
  }, [])

  function applyAnalysis(payload: AnalysisPayload): void {
    setAnalysis(payload)
    setRepositoryUrl(payload.repository.url)
    setSelectedFlowId(payload.flows[0]?.id ?? null)
    setOrders({})
    setResults({})
    setError(null)
  }

  const selectedFlow = useMemo<Flow | null>(
    () => analysis?.flows.find((flow) => flow.id === selectedFlowId) ?? null,
    [analysis, selectedFlowId],
  )

  const flowGraph = useMemo<CodeGraph | null>(
    () => (analysis && selectedFlow ? subGraphForFlow(analysis.graph, selectedFlow) : null),
    [analysis, selectedFlow],
  )

  const handleAnalyze = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const payload = await createAnalysis(repositoryUrl)
      applyAnalysis(payload)
      window.history.replaceState({}, '', `/?analysis_id=${payload.analysisId}`)
    } catch (apiError) {
      setAnalysis(null)
      setError((apiError as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const currentOrder = selectedFlow ? orders[selectedFlow.id] ?? [] : []
  const currentResult = selectedFlow ? results[selectedFlow.id] : undefined

  const handleSelectNode = (nodeId: string) => {
    if (!selectedFlow || currentResult) return
    setOrders((current) => ({
      ...current,
      [selectedFlow.id]: toggleOrder(current[selectedFlow.id] ?? [], nodeId),
    }))
  }

  const handleReset = () => {
    if (!selectedFlow) return
    setOrders((current) => ({ ...current, [selectedFlow.id]: [] }))
    setResults((current) => ({ ...current, [selectedFlow.id]: undefined }))
  }

  const handleSubmit = async () => {
    if (!analysis || !selectedFlow) return
    setLoading(true)
    setError(null)
    try {
      const result = await scoreFlow(analysis.analysisId, selectedFlow.id, currentOrder)
      setResults((current) => ({ ...current, [selectedFlow.id]: result }))
    } catch (apiError) {
      setError((apiError as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const stepLabel = (nodeId: string): string =>
    selectedFlow?.steps.find((step) => step.id === nodeId)?.path ?? nodeId

  return (
    <div className="space-y-8">
      <form onSubmit={handleAnalyze} className="space-y-3">
        <label className="block text-sm font-semibold text-slate-200" htmlFor="repository-url">
          Public GitHub repository URL
        </label>
        <div className="flex flex-col gap-3 md:flex-row">
          <input
            id="repository-url"
            value={repositoryUrl}
            onChange={(event) => setRepositoryUrl(event.target.value)}
            placeholder="https://github.com/owner/repo"
            className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-slate-100 outline-none transition focus:border-cyan-400"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-2xl bg-cyan-400 px-6 py-3 font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:text-slate-200"
          >
            {loading ? 'Mapping…' : 'Map repository'}
          </button>
        </div>
        <p className="text-sm text-slate-400">
          Example: https://github.com/wu4f/ralph-wiggum-tutorial
        </p>
      </form>

      {error ? (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      {analysis ? (
        <section className="space-y-8">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-3xl border border-slate-700 bg-slate-950/50 p-5 text-sm text-slate-300">
            <span className="text-base font-semibold text-white">
              {analysis.repository.owner}/{analysis.repository.repo}
            </span>
            <span>{analysis.summary.fileCount} files analyzed</span>
            <span>{analysis.summary.languages.join(', ')}</span>
            <span>{analysis.summary.flowCount} execution flow(s)</span>
          </div>

          {!analysis.flowsAvailable || !selectedFlow || !flowGraph ? (
            <div className="rounded-3xl border border-slate-700 bg-slate-900 px-5 py-4 text-slate-300">
              No execution flow could be detected for this repository. Try a web
              app repository with routed pages or a clear module entry point.
            </div>
          ) : (
            <>
              {analysis.flows.length > 1 ? (
                <div className="flex flex-wrap gap-2">
                  {analysis.flows.map((flow) => (
                    <button
                      key={flow.id}
                      type="button"
                      onClick={() => setSelectedFlowId(flow.id)}
                      className={`rounded-full border px-4 py-2 text-sm ${
                        flow.id === selectedFlowId
                          ? 'border-cyan-300 bg-cyan-400/20 text-cyan-100'
                          : 'border-slate-700 bg-slate-900 text-slate-300'
                      }`}
                    >
                      {flow.title}
                    </button>
                  ))}
                </div>
              ) : null}

              <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
                <CodeMap
                  graph={flowGraph}
                  order={currentOrder}
                  onSelectNode={handleSelectNode}
                  correctOrderIds={
                    currentResult ? currentResult.correctOrder.map((step) => step.id) : null
                  }
                />

                <div className="space-y-4">
                  <div>
                    <p className="text-sm uppercase tracking-[0.25em] text-cyan-300">
                      {selectedFlow.trigger}
                    </p>
                    <h3 className="mt-1 text-xl font-semibold text-white">
                      {selectedFlow.title}
                    </h3>
                    <p className="mt-2 text-slate-300">{selectedFlow.prompt}</p>
                  </div>

                  <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                    <p className="text-sm font-semibold text-slate-200">Your order</p>
                    {currentOrder.length === 0 ? (
                      <p className="mt-2 text-sm text-slate-400">
                        Click nodes on the map to build the execution order.
                      </p>
                    ) : (
                      <ol className="mt-2 space-y-1 text-sm text-slate-200">
                        {currentOrder.map((nodeId, index) => (
                          <li key={nodeId}>
                            <span className="font-semibold text-cyan-300">{index + 1}.</span>{' '}
                            {stepLabel(nodeId)}
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => void handleSubmit()}
                      disabled={loading || currentOrder.length === 0 || Boolean(currentResult)}
                      className="rounded-2xl bg-white px-4 py-2 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:text-slate-300"
                    >
                      Check flow
                    </button>
                    <button
                      type="button"
                      onClick={handleReset}
                      className="rounded-2xl border border-slate-600 px-4 py-2 font-semibold text-slate-200"
                    >
                      Reset
                    </button>
                  </div>

                  {currentResult ? (
                    <div
                      className={`rounded-2xl border px-4 py-3 text-sm ${
                        currentResult.isCorrect
                          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
                          : 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                      }`}
                    >
                      <p className="font-semibold">
                        Score {currentResult.score}/{currentResult.maxScore}
                      </p>
                      <p>{currentResult.feedback}</p>
                      <ol className="mt-2 space-y-1">
                        {currentResult.correctOrder.map((step, index) => (
                          <li key={step.id}>
                            <span className="font-semibold text-emerald-300">{index + 1}.</span>{' '}
                            {step.path}
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                </div>
              </div>
            </>
          )}
        </section>
      ) : null}
    </div>
  )
}
