/**
 * Development-only stand-in for `POST /api/v1/assistant/chat/`, used when the app is started
 * with `VITE_ASSISTANT_MOCK=true` (e.g. before the backend endpoint exists). It follows the
 * contract shapes with fictional data; it is never bundled into production builds unless that
 * variable is set. Its answers are placeholders, not translated UI text.
 *
 * Keywords in the last question pick the answer: `429`, `503`, `400`, `offline` simulate the
 * errors; `journey` gives a journey card, `stop` a stops card; anything
 * else gives a departures card.
 */
import { ApiError } from '@/api/client'
import type { ChatRequest, ChatResponse, LineSummary } from '@/types/api'

const LINE_A: LineSummary = {
  id: 'mock:52',
  short_name: '52',
  vehicle_type: 'tram',
  group: 'tram_day',
  colour: '#1f6feb',
  text_colour: '#ffffff',
}

const LINE_B: LineSummary = {
  id: 'mock:179',
  short_name: '179',
  vehicle_type: 'bus',
  group: 'bus_day',
  colour: '#0b7a3e',
  text_colour: '#ffffff',
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })
}

function isoIn(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString()
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export async function mockSendChat(
  request: ChatRequest,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  await wait(900, signal)
  const question = (request.messages[request.messages.length - 1]?.text ?? '').toLowerCase()

  if (question.includes('429')) {
    throw new ApiError(429, 'rate_limited', 'Too many requests.', undefined, 30)
  }
  if (question.includes('503')) {
    throw new ApiError(503, 'assistant_unavailable', 'Assistant unavailable.')
  }
  if (question.includes('400')) {
    throw new ApiError(400, 'validation_error', 'Invalid request.')
  }
  if (question.includes('offline')) {
    throw new ApiError(0, 'network_error', 'Failed to fetch')
  }

  if (question.includes('journey')) {
    return {
      message: { role: 'assistant', text: 'Mock: here is one connection (fictional data).' },
      cards: [
        {
          type: 'journey',
          from: { name: 'Northgate', lat: 50.0606, lon: 19.933 },
          to: { name: 'Southfield', lat: 50.017, lon: 19.889 },
          itinerary: {
            id: 'mock-1',
            start: isoIn(3),
            end: isoIn(24),
            duration: 1260,
            transfers: 0,
            walk_distance: 300,
            walk_duration: 240,
            legs: [
              {
                mode: 'walk',
                start: isoIn(3),
                end: isoIn(7),
                duration: 240,
                distance: 300,
                from: { name: 'Northgate', stop_id: null, lat: 50.0606, lon: 19.933 },
                to: { name: 'Northgate Sq', stop_id: 'mock:s1', lat: 50.061, lon: 19.9325 },
                line: null,
                headsign: null,
                trip_id: null,
                intermediate_stops: [],
                geometry: {
                  type: 'LineString',
                  coordinates: [
                    [19.933, 50.0606],
                    [19.9325, 50.061],
                  ],
                },
              },
              {
                mode: 'tram',
                start: isoIn(7),
                end: isoIn(24),
                duration: 1020,
                distance: 5200,
                from: { name: 'Northgate Sq', stop_id: 'mock:s1', lat: 50.061, lon: 19.9325 },
                to: { name: 'Southfield', stop_id: 'mock:s9', lat: 50.017, lon: 19.889 },
                line: LINE_A,
                headsign: 'Southfield',
                trip_id: 'mock:t1',
                intermediate_stops: [{ name: 'Midtown', stop_id: 'mock:s2' }],
                geometry: {
                  type: 'LineString',
                  coordinates: [
                    [19.9325, 50.061],
                    [19.889, 50.017],
                  ],
                },
              },
            ],
          },
          comparison: { walk: { duration: 4200, distance: 5600 }, bike: null },
        },
      ],
    }
  }

  if (question.includes('stop')) {
    return {
      message: { role: 'assistant', text: 'Mock: which stop do you mean?' },
      cards: [
        {
          type: 'stops',
          stops: ['Northgate', 'Northgate Sq', 'Northgate Depot'].map((name, i) => ({
            stop_id: `mock:s${i + 1}`,
            name,
            lat: 50.06,
            lon: 19.93,
            vehicle_types: i === 2 ? ['bus'] : ['tram', 'bus'],
            stop_ids: [`mock:s${i + 1}`],
          })),
        },
        { type: 'unknown_future_card', anything: true },
      ],
    }
  }

  return {
    message: { role: 'assistant', text: 'Mock: the next departures from Northgate Sq.' },
    cards: [
      {
        type: 'departures',
        stop: { stop_id: 'mock:s1', name: 'Northgate Sq' },
        departures: [
          ['08:14', LINE_A, 'Southfield'],
          ['08:19', LINE_B, 'Airport'],
          ['08:26', LINE_A, 'Southfield'],
        ].map(([time, line, headsign], i) => ({
          stop_id: i === 1 ? 'mock:s1b' : 'mock:s1',
          line,
          direction: 0,
          headsign,
          time,
          next_day: false,
          date: today(),
          trip_id: `mock:t${i}`,
        })),
      },
    ],
  }
}
