import { describe, expect, it } from 'vitest'
import i18n from './index'

describe('provider count', () => {
  it.each(['en', 'zh'])('interpolates the configured count in %s', lng => {
    const text = i18n.t('providers.configuredCount', { lng, count: 3 })
    expect(text).toContain('3')
    expect(text).not.toContain('{count}')
  })
})
