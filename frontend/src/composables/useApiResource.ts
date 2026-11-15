import { onBeforeUnmount, ref, shallowRef, watch, type Ref, type ShallowRef } from 'vue'

export type ResourceStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface ApiResource<T> {
  data: ShallowRef<T | null>
  status: Ref<ResourceStatus>
  error: ShallowRef<unknown>
  /** Fetches again with the current key (retry button). */
  reload: () => void
}

function isAbortError(err: unknown): boolean {
  return (
    typeof err === 'object' && err !== null && (err as { name?: unknown }).name === 'AbortError'
  )
}

/**
 * Loads data for a reactive key. Whenever the key changes (compared as JSON) the previous request
 * is aborted and a new request starts; a `null` key means "nothing to load" (status `idle`).
 * Requests are aborted when the component unmounts.
 *
 * By default the old data is cleared when the key changes. With `keepPrevious` it stays while the
 * new request loads (status `loading`), so controls rendered from it are not unmounted (keyboard
 * focus, map instances); it is still cleared on error.
 */
export function useApiResource<K, T>(
  key: () => K | null,
  fetcher: (key: K, signal: AbortSignal) => Promise<T>,
  options: { keepPrevious?: boolean } = {},
): ApiResource<T> {
  const data = shallowRef<T | null>(null)
  const status = ref<ResourceStatus>('idle')
  const error = shallowRef<unknown>(null)
  let controller: AbortController | null = null

  async function load(current: K | null): Promise<void> {
    controller?.abort()
    controller = null
    if (current === null) {
      data.value = null
      error.value = null
      status.value = 'idle'
      return
    }
    const own = new AbortController()
    controller = own
    status.value = 'loading'
    error.value = null
    try {
      const result = await fetcher(current, own.signal)
      if (own.signal.aborted) return
      data.value = result
      status.value = 'ready'
    } catch (err) {
      if (own.signal.aborted || isAbortError(err)) return
      data.value = null
      error.value = err
      status.value = 'error'
    } finally {
      if (controller === own) controller = null
    }
  }

  watch(
    () => {
      const current = key()
      return current === null ? null : JSON.stringify(current)
    },
    () => {
      if (!options.keepPrevious) data.value = null
      void load(key())
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    controller?.abort()
    controller = null
  })

  return { data, status, error, reload: () => void load(key()) }
}
