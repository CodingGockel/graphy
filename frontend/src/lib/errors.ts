import type { ApiError } from '../api/client'
import { t } from '../i18n'

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
