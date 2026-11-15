import { useI18n } from 'vue-i18n'

import { OSM_COPYRIGHT_URL } from '@/config/map'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Translated MapLibre texts shared by all maps: the OSM attribution HTML and MapLibre's own UI
 * strings. Both are fixed when a map is constructed, so maps rebuild on a language change.
 */
export function useMapI18n() {
  const { t, locale } = useI18n()

  function attributionHtml(): string {
    return `&copy; <a href="${OSM_COPYRIGHT_URL}" target="_blank" rel="noopener">${escapeHtml(
      t('map.osmContributors'),
    )}</a>`
  }

  function mapLocale(): Record<string, string> {
    return {
      'Map.Title': t('map.controls.title'),
      'NavigationControl.ZoomIn': t('map.controls.zoomIn'),
      'NavigationControl.ZoomOut': t('map.controls.zoomOut'),
      'NavigationControl.ResetBearing': t('map.controls.resetBearing'),
      'AttributionControl.ToggleAttribution': t('map.controls.toggleAttribution'),
      'AttributionControl.MapFeedback': t('map.controls.mapFeedback'),
      'GeolocateControl.FindMyLocation': t('map.controls.findMyLocation'),
      'GeolocateControl.LocationNotAvailable': t('map.controls.locationNotAvailable'),
      'Popup.Close': t('map.controls.popupClose'),
      'CooperativeGesturesHandler.WindowsHelpText': t('map.controls.cooperativeWindows'),
      'CooperativeGesturesHandler.MacHelpText': t('map.controls.cooperativeMac'),
      'CooperativeGesturesHandler.MobileHelpText': t('map.controls.cooperativeMobile'),
    }
  }

  return { t, locale, attributionHtml, mapLocale }
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}
