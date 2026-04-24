import { NextResponse } from 'next/server'

function getApiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
}

export async function GET() {
  return NextResponse.redirect(`${getApiBaseUrl()}/api/auth/login`)
}
