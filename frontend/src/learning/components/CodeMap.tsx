import { useMemo } from 'react'

import type { CodeGraph } from '@/learning/types'

type Props = {
  graph: CodeGraph
  order: string[]
  onSelectNode: (nodeId: string) => void
  correctOrderIds?: string[] | null
}

type PositionedNode = {
  id: string
  label: string
  kind: string
  x: number
  y: number
}

const WIDTH = 760
const HEIGHT = 520
const RADIUS = 200
const NODE_RADIUS = 30

export function CodeMap({ graph, order, onSelectNode, correctOrderIds }: Props) {
  const positioned = useMemo<PositionedNode[]>(() => {
    const centerX = WIDTH / 2
    const centerY = HEIGHT / 2
    const count = graph.nodes.length || 1
    return graph.nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / count - Math.PI / 2
      return {
        id: node.id,
        label: node.label,
        kind: node.kind,
        x: centerX + RADIUS * Math.cos(angle),
        y: centerY + RADIUS * Math.sin(angle),
      }
    })
  }, [graph.nodes])

  const positionMap = useMemo(
    () => new Map(positioned.map((node) => [node.id, node])),
    [positioned],
  )

  const revealing = Boolean(correctOrderIds && correctOrderIds.length > 0)

  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-700 bg-slate-950/70 p-4">
      <svg
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="mx-auto block min-w-[640px]"
        aria-label="Repository execution map"
      >
        <defs>
          <marker
            id="flow-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#34d399" />
          </marker>
        </defs>

        {graph.edges.map((edge) => {
          const source = positionMap.get(edge.sourceId)
          const target = positionMap.get(edge.targetId)
          if (!source || !target) return null
          return (
            <line
              key={edge.id}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke="#334155"
              strokeWidth="2"
            />
          )
        })}

        {revealing
          ? correctOrderIds!.slice(0, -1).map((nodeId, index) => {
              const source = positionMap.get(nodeId)
              const target = positionMap.get(correctOrderIds![index + 1])
              if (!source || !target) return null
              return (
                <line
                  key={`correct-${nodeId}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke="#34d399"
                  strokeWidth="3"
                  markerEnd="url(#flow-arrow)"
                />
              )
            })
          : null}

        {positioned.map((node) => {
          const selectedIndex = order.indexOf(node.id)
          const correctIndex = correctOrderIds
            ? correctOrderIds.indexOf(node.id)
            : -1
          const badge = revealing
            ? correctIndex >= 0
              ? correctIndex + 1
              : null
            : selectedIndex >= 0
              ? selectedIndex + 1
              : null
          const fill = revealing
            ? correctIndex >= 0
              ? '#065f46'
              : '#0f172a'
            : selectedIndex >= 0
              ? '#0891b2'
              : '#0f172a'
          const stroke = revealing
            ? '#34d399'
            : selectedIndex >= 0
              ? '#67e8f9'
              : '#475569'
          return (
            <g
              key={node.id}
              onClick={() => onSelectNode(node.id)}
              className="cursor-pointer"
              role="button"
              aria-label={`${node.label} (${node.kind})`}
            >
              <circle
                cx={node.x}
                cy={node.y}
                r={NODE_RADIUS}
                fill={fill}
                stroke={stroke}
                strokeWidth="2.5"
              />
              {badge !== null ? (
                <>
                  <circle cx={node.x + 22} cy={node.y - 22} r="11" fill={revealing ? '#34d399' : '#67e8f9'} />
                  <text
                    x={node.x + 22}
                    y={node.y - 18}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="700"
                    fill="#0f172a"
                  >
                    {badge}
                  </text>
                </>
              ) : null}
              <text
                x={node.x}
                y={node.y + 2}
                textAnchor="middle"
                fontSize="10"
                fontWeight="700"
                fill="white"
              >
                {node.label.length > 12 ? `${node.label.slice(0, 11)}…` : node.label}
              </text>
              <text
                x={node.x}
                y={node.y + NODE_RADIUS + 14}
                textAnchor="middle"
                fontSize="9"
                fill="#94a3b8"
              >
                {node.kind}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
