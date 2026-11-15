import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import en from '@/locales/en.json'
import pl from '@/locales/pl.json'

type Tree = { [key: string]: string | Tree }

function flatten(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'object' ? flatten(value, path) : [path]
  })
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    return statSync(full).isDirectory() ? sourceFiles(full) : /\.(vue|ts)$/.test(name) ? [full] : []
  })
}

const root = join(__dirname, '..', '..', 'src')
const files = [
  join(root, 'components', 'LoadStatus.vue'),
  ...sourceFiles(join(root, 'components', 'timetable')),
  ...sourceFiles(join(root, 'views', 'timetable')),
  ...sourceFiles(join(root, 'composables')),
]

describe('timetable locale keys', () => {
  const plKeys = new Set(flatten(pl as Tree))
  const enKeys = new Set(flatten(en as Tree))

  it('timetable section has identical keys in pl and en', () => {
    const only = (keys: Set<string>) => [...keys].filter((k) => k.startsWith('timetable.')).sort()
    expect(only(enKeys)).toEqual(only(plKeys))
    expect(only(plKeys).length).toBeGreaterThan(20)
  })

  it('every literal key used by the timetable code exists in both languages', () => {
    const used = new Set<string>()
    for (const file of files) {
      const text = readFileSync(file, 'utf8')
      for (const m of text.matchAll(/\bt\(\s*['"`]((?:timetable|errors|common)\.[\w.]+)['"`]/g)) {
        used.add(m[1]!)
      }
    }
    expect(used.size).toBeGreaterThan(30)
    for (const key of used) {
      expect(plKeys.has(key), `pl missing ${key}`).toBe(true)
      expect(enKeys.has(key), `en missing ${key}`).toBe(true)
    }
  })

  it('dynamic keys cover every value (vehicle types, day types, variant kinds)', () => {
    const keys = [
      ...['tram', 'bus', 'metro', 'rail'].flatMap((v) => [
        `timetable.vehicleTypes.${v}`,
        `timetable.vehicleType.${v}`,
      ]),
      ...['weekday', 'saturday', 'sunday'].map((d) => `timetable.dayTypes.${d}`),
      ...['short_turn', 'depot', 'other'].map((k) => `timetable.variantKinds.${k}`),
      'timetable.notice.detour',
      'timetable.notice.change',
    ]
    for (const key of keys) {
      expect(plKeys.has(key), `pl missing ${key}`).toBe(true)
      expect(enKeys.has(key), `en missing ${key}`).toBe(true)
    }
  })
})
