import { mount } from '@vue/test-utils'

import CityMap from '@/components/CityMap.vue'
import { i18n } from '@/i18n'

import { cityList } from './citiesFixtures'

const mapCtor = vi.hoisted(() => vi.fn())

vi.mock('maplibre-gl', () => ({
  Map: class {
    constructor(opts: unknown) {
      mapCtor(opts)
    }
    addControl() {}
    remove() {}
  },
  NavigationControl: class {},
}))
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}))

describe('CityMap', () => {
  it('starts at the centre and zoom from the API, in [lon, lat] order', () => {
    const wrapper = mount(CityMap, {
      props: { city: cityList()[0]! },
      global: { plugins: [i18n] },
    })
    expect(mapCtor).toHaveBeenCalledTimes(1)
    const opts = mapCtor.mock.calls[0]![0] as { center: [number, number]; zoom: number }
    expect(opts.center).toEqual([20.25, 10.5])
    expect(opts.zoom).toBe(11)
    expect(wrapper.attributes('data-city')).toBe('alpha')
    wrapper.unmount()
  })
})
