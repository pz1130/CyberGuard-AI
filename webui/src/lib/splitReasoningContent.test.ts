import { describe, expect, it } from 'vitest'
import { splitReasoningContent } from './splitReasoningContent'

describe('splitReasoningContent', () => {
  it('collapses bare think and reasoning tags', () => {
    const { reasoning, answer } = splitReasoningContent(
      '<think>secret</think>visible <reasoning>r</reasoning>ok',
    )
    expect(reasoning).toEqual(['secret', 'r'])
    expect(answer).toContain('visible')
    expect(answer).toContain('ok')
    expect(answer).not.toContain('secret')
  })

  it('accepts MiniMax/Qwen/DeepSeek think-tag variants', () => {
    for (const raw of [
      '<think>0\nhidden</think>\nvisible',
      '<think_1>hidden</think>visible',
      '<think abc>hidden</think>visible',
    ]) {
      const { reasoning, answer } = splitReasoningContent(raw)
      expect(reasoning.some((part) => part.includes('hidden'))).toBe(true)
      expect(answer).toContain('visible')
      expect(answer).not.toContain('hidden')
      expect(answer.toLowerCase()).not.toContain('<think')
    }
  })
})
