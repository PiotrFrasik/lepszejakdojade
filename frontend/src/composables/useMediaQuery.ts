import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/** Whether a CSS media query matches, kept up to date while the component is mounted. */
export function useMediaQuery(query: string): Ref<boolean> {
  const matches = ref(false)
  let media: MediaQueryList | null = null

  function onChange(event: MediaQueryListEvent): void {
    matches.value = event.matches
  }

  onMounted(() => {
    if (typeof window.matchMedia !== 'function') return
    media = window.matchMedia(query)
    matches.value = media.matches
    media.addEventListener?.('change', onChange)
  })

  onBeforeUnmount(() => {
    media?.removeEventListener?.('change', onChange)
  })

  return matches
}
