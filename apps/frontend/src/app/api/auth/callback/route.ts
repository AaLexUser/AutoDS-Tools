import { NextRequest, NextResponse } from 'next/server'

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
}

export async function GET(request: NextRequest) {
  const target = new URL(`${getApiBaseUrl()}/api/auth/callback`)
  const code = request.nextUrl.searchParams.get('code')
  const error = request.nextUrl.searchParams.get('error')
  const errorDescription = request.nextUrl.searchParams.get('error_description')

  if (code) {
    target.searchParams.set('code', code)
  }
  if (error) {
    target.searchParams.set('error', error)
  }
  if (errorDescription) {
    target.searchParams.set('error_description', errorDescription)
  }

  return NextResponse.redirect(target)
}
