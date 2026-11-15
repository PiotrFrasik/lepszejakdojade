import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** i18n key of the page title (used for `document.title`). */
    titleKey?: string
    /** Page fills the viewport (full-screen map): no footer, no page scrolling. */
    fullscreen?: boolean
  }
}

// Lazy-loaded so the large MapLibre bundle does not block the app shell.
const HomeView = () => import('@/views/HomeView.vue')
const PlaceholderView = () => import('@/views/PlaceholderView.vue')

export const routes: RouteRecordRaw[] = [
  // Home is the journey planner (#13): full-screen map with the search panel.
  {
    path: '/',
    name: 'home',
    component: HomeView,
    meta: { titleKey: 'nav.journey', fullscreen: true },
  },
  { path: '/journey', name: 'journey', redirect: { name: 'home' } },
  // Timetable browser (#11). Ids are opaque API ids; `?type=`, `?direction=1` and `?date=` keep
  // the tab, direction and service date in the URL. The city is not in the URL (it comes from the
  // city store), so a shared line or stop link only works for someone with the same city selected;
  // switching city sends the user back to `/timetable`.
  {
    path: '/timetable',
    name: 'timetable',
    component: () => import('@/views/timetable/TimetableHomeView.vue'),
    meta: { titleKey: 'nav.timetable' },
  },
  {
    path: '/timetable/lines/:lineId',
    name: 'timetable-line',
    component: () => import('@/views/timetable/LineView.vue'),
    meta: { titleKey: 'timetable.lineDiagram' },
  },
  {
    path: '/timetable/lines/:lineId/stops/:stopId',
    name: 'timetable-stop',
    component: () => import('@/views/timetable/StopTimetableView.vue'),
    meta: { titleKey: 'timetable.stopTimetable' },
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
    component: () => import('@/views/DataSourcesView.vue'),
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
