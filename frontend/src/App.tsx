import { Refine, useCustom } from '@refinedev/core'

import logo from '@/assets/vyom-logo.png'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { dataProvider } from '@/dataProvider'

type Health = { status: string; service: string; version: string }

function BackendHealth() {
  const { query } = useCustom<Health>({
    url: '/api/health',
    method: 'get',
    queryOptions: { retry: false, refetchInterval: 10_000 },
    errorNotification: false,
  })
  const health = query.data?.data

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          Backend
          {query.isPending ? (
            <Badge variant="secondary">Checking</Badge>
          ) : query.isError ? (
            <Badge variant="destructive">Unreachable</Badge>
          ) : (
            <Badge>{health?.status}</Badge>
          )}
        </CardTitle>
        <CardDescription>Process liveness of the Vyom API.</CardDescription>
      </CardHeader>
      <CardContent>
        {query.isError ? (
          <Alert variant="destructive">
            <AlertTitle>{query.error.message}</AlertTitle>
            <AlertDescription>
              Start the backend on 127.0.0.1:8000; this page retries every 10 seconds.
            </AlertDescription>
          </Alert>
        ) : (
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Service</dt>
            <dd>{health?.service ?? '—'}</dd>
            <dt className="text-muted-foreground">Version</dt>
            <dd>{health?.version ?? '—'}</dd>
          </dl>
        )}
      </CardContent>
    </Card>
  )
}

function App() {
  return (
    <Refine dataProvider={dataProvider} options={{ disableTelemetry: true }}>
      <div className="min-h-svh bg-background text-foreground">
        <header className="border-b">
          <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
            <img src={logo} alt="" className="h-9 w-auto" />
            <span className="text-lg font-semibold">Vyom</span>
          </div>
        </header>
        <main className="mx-auto max-w-3xl px-4 py-8">
          <BackendHealth />
        </main>
      </div>
    </Refine>
  )
}

export default App
