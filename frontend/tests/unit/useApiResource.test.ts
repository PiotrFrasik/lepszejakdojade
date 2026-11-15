import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

import { useApiResource } from '@/composables/useApiResource'

interface Pending {
  key: number
  signal: AbortSignal
  resolve: (v: string) => void
  reject: (e: unknown) => void
}

function setup(options: { keepPrevious?: boolean } = {}) {
  const key = ref<number | null>(1)
  const pending: Pending[] = []
  let resource!: ReturnType<typeof useApiResource<number, string>>
  const wrapper = mount(
    defineComponent({
      setup() {
        resource = useApiResource<number, string>(
          () => key.value,
          (k, signal) =>
            new Promise<string>((resolve, reject) =>
              pending.push({ key: k, signal, resolve, reject }),
            ),
          options,
        )
        return () => h('div')
      },
    }),
  )
  return { key, pending, wrapper, resource }
}

describe('useApiResource', () => {
  it('loads for the key and becomes ready', async () => {
    const { pending, resource } = setup()
    expect(resource.status.value).toBe('loading')
    pending[0]!.resolve('one')
    await flushPromises()
    expect(resource.status.value).toBe('ready')
    expect(resource.data.value).toBe('one')
  })

  it('clears old data on key change by default', async () => {
    const { key, pending, resource } = setup()
    pending[0]!.resolve('one')
    await flushPromises()
    key.value = 2
    await flushPromises()
    expect(resource.data.value).toBeNull()
    expect(resource.status.value).toBe('loading')
  })

  it('keepPrevious keeps old data while the new request loads', async () => {
    const { key, pending, resource } = setup({ keepPrevious: true })
    pending[0]!.resolve('one')
    await flushPromises()
    key.value = 2
    await flushPromises()
    expect(resource.status.value).toBe('loading')
    expect(resource.data.value).toBe('one')
    pending[1]!.resolve('two')
    await flushPromises()
    expect(resource.data.value).toBe('two')
  })

  it('keepPrevious still clears data on error', async () => {
    const { key, pending, resource } = setup({ keepPrevious: true })
    pending[0]!.resolve('one')
    await flushPromises()
    key.value = 2
    await flushPromises()
    pending[1]!.reject(new Error('boom'))
    await flushPromises()
    expect(resource.status.value).toBe('error')
    expect(resource.data.value).toBeNull()
  })

  it('aborts the previous request on key change and ignores its stale response', async () => {
    const { key, pending, resource } = setup({ keepPrevious: true })
    key.value = 2
    await flushPromises()
    expect(pending[0]!.signal.aborted).toBe(true)
    pending[1]!.resolve('two')
    await flushPromises()
    pending[0]!.resolve('stale')
    await flushPromises()
    expect(resource.data.value).toBe('two')
    expect(resource.status.value).toBe('ready')
  })

  it('ignores a stale error from an aborted request', async () => {
    const { key, pending, resource } = setup()
    key.value = 2
    await flushPromises()
    pending[1]!.resolve('two')
    pending[0]!.reject(new Error('late'))
    await flushPromises()
    expect(resource.status.value).toBe('ready')
    expect(resource.error.value).toBeNull()
  })

  it('aborts the in-flight request on unmount', () => {
    const { pending, wrapper } = setup()
    wrapper.unmount()
    expect(pending[0]!.signal.aborted).toBe(true)
  })

  it('a null key means idle', async () => {
    const { key, pending, resource } = setup()
    pending[0]!.resolve('one')
    await flushPromises()
    key.value = null
    await flushPromises()
    expect(resource.status.value).toBe('idle')
    expect(resource.data.value).toBeNull()
  })
})
