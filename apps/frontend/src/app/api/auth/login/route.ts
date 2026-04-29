import { NextResponse } from 'next/server'
import { getApiBaseUrl } from '@/lib/api/base-url'

export async function GET() {
  return NextResponse.redirect(`${getApiBaseUrl()}/api/auth/login`)
}
