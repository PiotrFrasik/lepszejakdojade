import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** i18n key of the page title (used for `document.title`). */
    titleKey?: string
  }
}

// Lazy-loaded so the large MapLibre bundle does not block the app shell.
const HomeView = () => import('@/views/HomeView.vue')
const PlaceholderView = () => import('@/views/PlaceholderView.vue')

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomeView, meta: { titleKey: 'nav.home' } },
  {
    path: '/journey',
    name: 'journey',
    component: PlaceholderView,
    meta: { titleKey: 'nav.journey' },
  },
  {
    path: '/timetable',
    name: 'timetable',
    component: PlaceholderView,
    meta: { titleKey: 'nav.timetable' },
  },
  {
    path: '/tickets',
    name: 'tickets',
    component: PlaceholderView,
    meta: { titleKey: 'nav.tickets' },
  },
  {
    path: '/assistant',
    name: 'assistant',
    component: PlaceholderView,
    meta: { titleKey: 'nav.assistant' },
  },
  {
    path: '/data-sources',
    name: 'data-sources',
    component: PlaceholderView,
    meta: { titleKey: 'nav.dataSources' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { titleKey: 'notFound.title' },
  },
]

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
