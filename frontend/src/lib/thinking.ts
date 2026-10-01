export interface SplitAnswer {
  /** The model's reasoning, or null if there is none. */
  thinking: string | null
  answer: string
}

const OPEN = '<think>'
const CLOSE = '</think>'

/**
 * Separates `<think>…</think>` reasoning from an LLM answer.
 *
 * Handles several blocks, an unclosed block (truncated output) and a lone closing tag:
 * some chat templates put the opening `<think>` into the prompt, so the output only
 * contains the reasoning followed by `</think>`.
 */
export function splitThinking(content: string): SplitAnswer {
  const parts: string[] = []
  let rest = content

  const close = rest.indexOf(CLOSE)
  const open = rest.indexOf(OPEN)
  if (close !== -1 && (open === -1 || open > close)) {
    parts.push(rest.slice(0, close))
    rest = rest.slice(close + CLOSE.length)
  }

  rest = rest.replace(/<think>([\s\S]*?)(?:<\/think>|$)/g, (_match, inner: string) => {
    parts.push(inner)
    return ''
  })

  const thinking = parts
    .map((part) => part.trim())
    .filter(Boolean)
    .join('\n\n')
  return { thinking: thinking || null, answer: rest.trim() }
}
