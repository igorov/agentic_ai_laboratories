'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { HistoryItem } from '../_lib/api-client'

interface ChatMessageProps {
  item: HistoryItem
  onFeedback: (traceId: string, isOk: boolean) => void
}

function feedbackButtonClass(active: boolean) {
  return `rounded-md p-1 transition-colors hover:bg-zinc-100 ${
    active ? 'text-zinc-900' : 'text-zinc-400 hover:text-zinc-700'
  }`
}

export default function ChatMessage({ item, onFeedback }: ChatMessageProps) {
  const canGiveFeedback = item.trace_id !== '__pending__' && item.answer !== ''

  return (
    <div className="flex flex-col gap-2">
      {/* Pregunta del usuario */}
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-zinc-100 px-4 py-2.5 text-sm text-zinc-900">
          {item.question}
        </div>
      </div>

      {/* Respuesta del agente */}
      <div className="flex justify-start">
        <div className="max-w-[75%] rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-2.5 text-sm text-zinc-800">
          {item.answer
            ? <div className="prose prose-sm prose-zinc max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.answer}</ReactMarkdown>
              </div>
            : <p className="text-zinc-400">Pensando…</p>
          }
        </div>
      </div>

      {/* Feedback: se liga al trace_id (run_id del trace en LangSmith) */}
      {canGiveFeedback && (
        <div className="flex gap-1 pl-1">
          <button
            onClick={() => onFeedback(item.trace_id, true)}
            title="Buena respuesta"
            aria-pressed={item.is_ok === true}
            className={feedbackButtonClass(item.is_ok === true)}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill={item.is_ok === true ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 10v12" />
              <path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z" />
            </svg>
          </button>
          <button
            onClick={() => onFeedback(item.trace_id, false)}
            title="Mala respuesta"
            aria-pressed={item.is_ok === false}
            className={feedbackButtonClass(item.is_ok === false)}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill={item.is_ok === false ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 14V2" />
              <path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}
