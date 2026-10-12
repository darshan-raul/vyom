import { Refine } from '@refinedev/core'
import { BrowserRouter, Route, Routes } from 'react-router'

import { Sidebar } from '@/components/vyom/sidebar'
import { dataProvider } from '@/dataProvider'
import { useApiHealth } from '@/lib/api-health'
import { Kubernetes } from '@/pages/kubernetes'
import { Today } from '@/pages/today'

// Sidebar + main as a wrapping row (DESIGN.md §3): the sidebar stacks above on narrow screens.
function Console() {
  const api = useApiHealth()

  return (
    <div className="mx-auto flex max-w-[1440px] flex-wrap items-start gap-5 p-5">
      <Sidebar api={api} />
      <main className="flex min-w-0 flex-[999_1_560px] flex-col gap-7 px-1 pt-2.5 pb-8">
        <Routes>
          <Route path="/" element={<Today api={api} />} />
          <Route path="/kubernetes" element={<Kubernetes />} />
          <Route path="*" element={<Today api={api} />} />
        </Routes>
      </main>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Refine dataProvider={dataProvider} options={{ disableTelemetry: true }}>
        <Console />
      </Refine>
    </BrowserRouter>
  )
}

export default App
