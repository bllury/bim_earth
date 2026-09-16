import { ref } from 'vue'

export type ConsoleLogLevel = 'info' | 'warn' | 'error'

export interface ConsoleLogEntry {
  id: number
  level: ConsoleLogLevel
  message: string
  detail?: string
  time: string
}

const MAX_ENTRIES = 300

const entries = ref<ConsoleLogEntry[]>([])
let nextEntryId = 1
let globalCaptureInstalled = false
let consoleBridgeInstalled = false

const nativeConsoleError = console.error.bind(console)
const nativeConsoleWarn = console.warn.bind(console)

/** Formats a log timestamp as HH:MM:SS. */
const formatTime = () =>
  new Date().toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

/** Renders arbitrary log details as a compact single line. */
const formatDetail = (detail: unknown): string | undefined => {
  if (detail === undefined || detail === null) return undefined
  if (typeof detail === 'string') return detail
  if (detail instanceof Error) return detail.message
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}

/** Turns raw console arguments into a message plus an optional detail. */
const formatConsoleArgs = (args: unknown[]) => {
  if (args.length === 0) return { message: '(空日志)', detail: undefined }

  const [first, ...rest] = args
  const message =
    typeof first === 'string' ? first : (formatDetail(first) ?? String(first))
  const detail =
    rest.length === 0 ? undefined : rest.length === 1 ? rest[0] : rest

  return { message, detail }
}

/** Appends one entry to the in-app console panel. */
export const pushConsoleLog = (
  level: ConsoleLogLevel,
  message: string,
  detail?: unknown,
) => {
  entries.value = [
    ...entries.value,
    {
      id: nextEntryId,
      level,
      message,
      detail: formatDetail(detail),
      time: formatTime(),
    },
  ].slice(-MAX_ENTRIES)
  nextEntryId += 1
}

/** Records an error both in the in-app console and in the browser console. */
export const logError = (message: string, detail?: unknown) => {
  nativeConsoleError(message, detail)
  pushConsoleLog('error', message, detail)
}

/** Records a warning both in the in-app console and in the browser console. */
export const logWarn = (message: string, detail?: unknown) => {
  nativeConsoleWarn(message, detail)
  pushConsoleLog('warn', message, detail)
}

/** Records an informational message in the in-app console. */
export const logInfo = (message: string, detail?: unknown) => {
  pushConsoleLog('info', message, detail)
}

/** Clears every entry from the in-app console panel. */
export const clearConsoleLogs = () => {
  entries.value = []
}

/** Mirrors uncaught browser errors into the in-app console panel. */
export const installGlobalConsoleCapture = () => {
  if (globalCaptureInstalled || typeof window === 'undefined') return
  globalCaptureInstalled = true

  window.addEventListener('error', (event) => {
    pushConsoleLog(
      'error',
      event.message || '未捕获的脚本错误',
      event.error ?? event.filename,
    )
  })

  window.addEventListener('unhandledrejection', (event) => {
    pushConsoleLog('error', '未处理的 Promise 拒绝', event.reason)
  })
}

/**
 * Mirrors `console.error` / `console.warn` output (Vue internals, Cesium,
 * third-party code) into the in-app console panel. Our own helpers call the
 * native console directly, so nothing is recorded twice.
 */
export const installConsoleBridge = () => {
  if (consoleBridgeInstalled || typeof window === 'undefined') return
  consoleBridgeInstalled = true

  console.error = (...args: unknown[]) => {
    nativeConsoleError(...args)
    const { message, detail } = formatConsoleArgs(args)
    pushConsoleLog('error', message, detail)
  }

  console.warn = (...args: unknown[]) => {
    nativeConsoleWarn(...args)
    const { message, detail } = formatConsoleArgs(args)
    pushConsoleLog('warn', message, detail)
  }
}

export const useAppConsole = () => ({
  entries,
  pushConsoleLog,
  logError,
  logWarn,
  logInfo,
  clearConsoleLogs,
})
