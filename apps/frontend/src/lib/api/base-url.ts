function stripTrailingSlash(value: string) {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

function isLocalBrowserHost(hostname: string) {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0'
}

export function getApiBaseUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return stripTrailingSlash(process.env.NEXT_PUBLIC_API_URL)
  }

  if (typeof window !== 'undefined') {
    if (isLocalBrowserHost(window.location.hostname)) {
      return `${window.location.protocol}//${window.location.hostname}:8000`
    }
    return stripTrailingSlash(window.location.origin)
  }

  return 'http://localhost:8000'
}
