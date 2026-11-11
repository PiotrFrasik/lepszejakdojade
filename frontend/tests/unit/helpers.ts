import { mount, type ComponentMountingOptions } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { applyLocale, i18n } from '@/i18n'
import { routes } from '@/router'

/** Mounts a component with a fresh pinia, the real i18n instance and a memory router. */
export async function mountApp(
  component: Component,
  options: ComponentMountingOptions<Component> = {},
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/journey')
  await router.isReady()
  const wrapper = mount(component, {
    ...options,
    global: {
      plugins: [pinia, i18n, router],
      stubs: { CityMap: true },
      ...(options.global ?? {}),
    },
  })
  return { wrapper, router, pinia }
}

export function resetEnvironment(): void {
  window.localStorage.clear()
  applyLocale('pl')
  window.localStorage.clear()
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
