import { STORAGE_KEYS, readStorage, removeStorage, writeStorage } from '@/utils/storage'

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('storage helpers', () => {
  it('write, read and remove a value', () => {
    writeStorage('k', 'v')
    expect(readStorage('k')).toBe('v')
    removeStorage('k')
    expect(readStorage('k')).toBeNull()
  })

  it('returns null for a missing key', () => {
    expect(readStorage('missing')).toBeNull()
  })

  it('survive a throwing localStorage', () => {
    const boom = () => {
      throw new Error('storage unavailable')
    }
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(boom)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(boom)
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(boom)
    expect(readStorage(STORAGE_KEYS.city)).toBeNull()
    expect(() => writeStorage(STORAGE_KEYS.city, 'krakow')).not.toThrow()
    expect(() => removeStorage(STORAGE_KEYS.city)).not.toThrow()
  })
})
