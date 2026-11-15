/**
 * Safe wrappers around `localStorage`.
 *
 * Storage can be unavailable (private mode, disabled cookies, quota exceeded, SSR/tests),
 * so every access is wrapped in try/catch and failures are silently ignored.
 */

export const STORAGE_KEYS = {
  city: 'ljd.city',
  locale: 'ljd.locale',
  timetableVehicleType: 'ljd.timetable.vehicleType',
} as const

export function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Ignore: the choice simply will not be remembered.
  }
}

export function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Ignore.
  }
}

/** Keys kept in `sessionStorage` (this browser tab only). */
export const SESSION_KEYS = {
  assistantConversation: 'ljd.assistant.conversation',
} as const

export function readSession(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    return null
  }
}

export function writeSession(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value)
  } catch {
    // Ignore: the value simply will not survive a reload.
  }
}

export function removeSession(key: string): void {
  try {
    window.sessionStorage.removeItem(key)
  } catch {
    // Ignore.
  }
}
