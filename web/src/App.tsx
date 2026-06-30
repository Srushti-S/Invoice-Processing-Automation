import { Header } from './components/Header'
import { Controls } from './components/Controls'
import { SummaryBar } from './components/SummaryBar'
import { ResultsTable } from './components/ResultsTable'
import { Sidebar } from './components/Sidebar'
import { DetailPanel } from './components/DetailPanel'
import { usePipeline } from './hooks/usePipeline'

export default function App() {
  const pipeline = usePipeline()
  return (
    <div className="mx-auto max-w-[1200px] px-4 py-6 sm:px-6 sm:py-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
        <Header />
        <Controls
          folder={pipeline.folder}
          provider={pipeline.provider}
          providers={pipeline.providers}
          loading={pipeline.loading}
          onFolder={pipeline.changeFolder}
          onProvider={pipeline.changeProvider}
          onRun={() => pipeline.runBatch()}
          onReset={pipeline.reset}
        />
      </header>

      {pipeline.summary && <SummaryBar summary={pipeline.summary} />}

      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[1fr_240px]">
        <ResultsTable results={pipeline.results} onSelect={pipeline.setSelected} />
        <Sidebar inventory={pipeline.inventory} fraudBlocked={pipeline.fraudBlocked} />
      </div>

      {pipeline.selected && (
        <DetailPanel
          result={pipeline.selected}
          onClose={() => pipeline.setSelected(null)}
          onOverride={pipeline.override}
        />
      )}
    </div>
  )
}
