'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  useAdminUsers,
  useApproveUser,
  useAuthState,
  useCliTokens,
  useCreateCliToken,
  useDisableUser,
  useRevokeCliToken,
} from '@/hooks/useAuth'

export default function AdminUsersPage() {
  const { data: authState, isLoading: isLoadingAuth } = useAuthState()
  const isAdmin = !!authState?.user?.is_admin
  const { data: users, isLoading: isLoadingUsers } = useAdminUsers(isAdmin)
  const { data: cliTokens } = useCliTokens(isAdmin)
  const approveUser = useApproveUser()
  const disableUser = useDisableUser()
  const createCliToken = useCreateCliToken()
  const revokeCliToken = useRevokeCliToken()
  const [tokenLabel, setTokenLabel] = useState('local-cli')
  const [lastCreatedToken, setLastCreatedToken] = useState<string | null>(null)

  if (isLoadingAuth) {
    return <div className="p-8 text-sm text-text-muted">Loading...</div>
  }

  if (authState?.mode === 'workos' && !isAdmin) {
    return (
      <div className="p-8">
        <p className="text-sm text-text-muted">Admin access required.</p>
        <Link href="/" className="mt-4 inline-block text-sm underline underline-offset-4">
          Back to AutoDS
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen w-full bg-background px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-text-primary">User approvals</h1>
            <p className="text-sm text-text-muted">
              Approve pending users and manage hosted CLI tokens.
            </p>
          </div>
          <Link href="/" className="text-sm underline underline-offset-4">
            Back to app
          </Link>
        </div>

        <section className="space-y-3 rounded-xl border border-border bg-background-secondary p-5">
          <h2 className="text-lg font-medium text-text-primary">Users</h2>
          {isLoadingUsers ? (
            <p className="text-sm text-text-muted">Loading users...</p>
          ) : (
            <div className="space-y-3">
              {users?.map((user) => (
                <div
                  key={user.id}
                  className="flex items-center justify-between gap-4 rounded-lg border border-border px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-text-primary">{user.email}</p>
                    <p className="text-xs text-text-muted">
                      {user.status}{user.is_admin ? ' · admin' : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {user.status !== 'approved' && (
                      <Button
                        size="sm"
                        onClick={() => approveUser.mutate(user.id)}
                        disabled={approveUser.isPending}
                      >
                        Approve
                      </Button>
                    )}
                    {user.status !== 'disabled' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => disableUser.mutate(user.id)}
                        disabled={disableUser.isPending}
                      >
                        Disable
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="space-y-3 rounded-xl border border-border bg-background-secondary p-5">
          <h2 className="text-lg font-medium text-text-primary">CLI tokens</h2>
          <div className="flex gap-2">
            <Input
              value={tokenLabel}
              onChange={(event) => setTokenLabel(event.target.value)}
              placeholder="Token label"
            />
            <Button
              onClick={async () => {
                const created = await createCliToken.mutateAsync(tokenLabel)
                setLastCreatedToken(created.token)
              }}
              disabled={createCliToken.isPending}
            >
              Create token
            </Button>
          </div>
          {lastCreatedToken && (
            <div className="rounded-lg border border-border px-4 py-3">
              <p className="text-xs text-text-muted">Copy this once. It will not be shown again.</p>
              <code className="mt-2 block break-all text-sm text-text-primary">{lastCreatedToken}</code>
            </div>
          )}
          <div className="space-y-2">
            {cliTokens?.map((token) => (
              <div
                key={token.id}
                className="flex items-center justify-between rounded-lg border border-border px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium text-text-primary">{token.label || 'CLI token'}</p>
                  <p className="text-xs text-text-muted">
                    Created {new Date(token.created_at).toLocaleString()}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => revokeCliToken.mutate(token.id)}
                  disabled={revokeCliToken.isPending}
                >
                  Revoke
                </Button>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
