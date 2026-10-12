import { Refine } from '@refinedev/core'

import { Sidebar } from '@/components/vyom/sidebar'
import { dataProvider } from '@/dataProvider'
import { useApiHealth } from '@/lib/api-health'
import { Today } from '@/pages/today'

// Sidebar + main as a wrapping row (DESIGN.md §3): the sidebar stacks above on narrow screens.
function Console() {
  const api = useApiHealth()

  return (
    <div className="mx-auto flex max-w-[1440px] flex-wrap items-start gap-5 p-5">
      <Sidebar api={api} />
      <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-7 px-1 pt-2.5 pb-8">
        <Today api={api} />
      </main>
    </div>
  )
}

function App() {
  return (
    <Refine dataProvider={dataProvider} options={{ disableTelemetry: true }}>
      <Console />
    </Refine>
  )
}

export default App
