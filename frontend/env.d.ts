/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dev-only fictional ticket data: `true`, `empty`, `fail` or `offline` (see `src/api/ticketsMock.ts`). */
  readonly VITE_TICKETS_MOCK?: string
}
