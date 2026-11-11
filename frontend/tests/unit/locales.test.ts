import en from '@/locales/en.json'
import pl from '@/locales/pl.json'

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') Object.assign(out, flatten(value, path))
    else out[path] = value
  }
  return out
}

describe('locale files', () => {
  const plFlat = flatten(pl as Tree)
  const enFlat = flatten(en as Tree)

  it('have identical key sets', () => {
    expect(Object.keys(enFlat).sort()).toEqual(Object.keys(plFlat).sort())
  })

  it('have only non-empty string values', () => {
    for (const [name, flat] of [
      ['pl', plFlat],
      ['en', enFlat],
    ] as const) {
      for (const [key, value] of Object.entries(flat)) {
        expect(typeof value, `${name}:${key}`).toBe('string')
        expect((value as string).trim(), `${name}:${key}`).not.toBe('')
      }
    }
  })

  it('use the same interpolation placeholders in both languages', () => {
    const placeholders = (s: unknown) => (String(s).match(/\{\w+\}/g) ?? []).sort()
    for (const key of Object.keys(plFlat)) {
      expect(placeholders(enFlat[key]), key).toEqual(placeholders(plFlat[key]))
    }
  })
})
