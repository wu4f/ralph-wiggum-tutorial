export type GraphNode = {
  id: string
  label: string
  path: string
  kind: string
}

export type GraphEdge = {
  id: string
  sourceId: string
  targetId: string
  label: string
}

export type CodeGraph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type FlowStep = {
  id: string
  label: string
  path: string
  kind: string
}

export type Flow = {
  id: string
  title: string
  trigger: string
  prompt: string
  steps: FlowStep[]
}

export type AnalysisSummary = {
  languages: string[]
  frameworks: { id: string; label: string }[]
  fileCount: number
  flowCount: number
}

export type AnalysisPayload = {
  analysisId: string
  expiresAt: string
  repository: {
    owner: string
    repo: string
    url: string
    defaultBranch: string
  }
  summary: AnalysisSummary
  graph: CodeGraph
  flows: Flow[]
  flowsAvailable: boolean
}

export type FlowScoreResult = {
  flowId: string
  score: number
  maxScore: number
  isCorrect: boolean
  feedback: string
  correctOrder: FlowStep[]
}
