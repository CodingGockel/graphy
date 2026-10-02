import { ApiError } from '../api/client'
import type { ChatErrorKind } from '../api/types'
import { t } from '../i18n'

// The HTTP status the backend uses for the same failure outside a stream.
const EVENT_STATUS: Record<ChatErrorKind, number> = {
  llm_unavailable: 503,
  llm_no_content: 502,
  sparql_unavailable: 503,
  sparql_failed: 502,
  internal: 500,
}

/** An `error` event of the chat stream as an `ApiError`, so it is shown like an HTTP error. */
export function errorFromEvent(kind: ChatErrorKind, message: string): ApiError {
  return new ApiError(EVENT_STATUS[kind] ?? 500, message)
}

/** A short, localized sentence for an API error. The raw backend message goes into details. */
export function errorHeadline(err: ApiError): string {
  switch (err.status) {
    case 0:
      return t('errors.network')
    case 404:
      return t('errors.notFound')
    case 502:
      return t('errors.upstream')
    case 503:
      return t('errors.unavailable')
    default:
      return t('errors.generic')
  }
}
