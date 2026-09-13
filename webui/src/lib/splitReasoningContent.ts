export interface ReasoningContent {
  reasoning: string[]
  answer: string
}

/** Split provider reasoning tags without exposing the raw XML-like markers. */
export function splitReasoningContent(content: string): ReasoningContent {
  const reasoning: string[] = []
  let answer = ''
  let cursor = 0
  // Same family as packages/llm_router/utils.py: <think>, <think>0, <think>_1.
  const openingTag = /<(think[^>]*|reasoning)>/gi
  let match: RegExpExecArray | null

  while ((match = openingTag.exec(content)) !== null) {
    answer += content.slice(cursor, match.index)
    const bodyStart = match.index + match[0].length
    const closeName = match[1].toLowerCase().startsWith('think') ? 'think' : 'reasoning'
    const closingTag = new RegExp(`</${closeName}>`, 'i')
    const closingMatch = closingTag.exec(content.slice(bodyStart))
    if (!closingMatch) {
      const partial = content.slice(bodyStart).trim()
      if (partial) reasoning.push(partial)
      cursor = content.length
      break
    }

    const body = content.slice(bodyStart, bodyStart + closingMatch.index).trim()
    if (body) reasoning.push(body)
    cursor = bodyStart + closingMatch.index + closingMatch[0].length
    openingTag.lastIndex = cursor
  }

  answer += content.slice(cursor)
  return { reasoning, answer: answer.replace(/<\/(?:think|reasoning)>/gi, '') }
}
