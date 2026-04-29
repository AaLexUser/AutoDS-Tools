function stripTrailingSlash(value: string) {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

export function getApiBaseUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return stripTrailingSlash(process.env.NEXT_PUBLIC_API_URL)
  }

  if (typeof window !== 'undefined') {
    return stripTrailingSlash(window.location.origin)
  }

  return 'http://localhost:8000'
}
