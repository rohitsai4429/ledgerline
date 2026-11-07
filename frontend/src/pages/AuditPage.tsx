import { useState } from 'react'
import { Search, ShieldCheck } from 'lucide-react'
import { ApiError } from '../api/client'
import { useAuditEvents } from '../hooks/useLedgerData'
import { Alert, Button, Card, EmptyState, Loading, PageHeader, StatusPill } from '../components/ui'

export function AuditPage() {
  const [actorInput, setActorInput] = useState('')
  const [actorFilter, setActorFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const pageSize = 25
  const events = useAuditEvents({
    actor_user_id: actorFilter || undefined,
    limit: pageSize,
    offset,
  })

  function applyFilter(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActorFilter(actorInput.trim())
    setOffset(0)
  }

  return (
    <>
      <PageHeader eyebrow="READ-ONLY OVERSIGHT" title="Audit events" description="Operation outcomes recorded by the backend audit service." action={<span className="admin-key"><ShieldCheck size={15} /> READ ONLY</span>} />
      <Card className="table-card">
        <form className="table-toolbar audit-filter" onSubmit={applyFilter}>
          <label className="filter-field">
            <span>Filter by actor user ID</span>
            <input value={actorInput} onChange={(event) => setActorInput(event.target.value)} placeholder="Optional UUID" />
          </label>
          <Button type="submit"><Search size={16} /> Apply filter</Button>
          {actorFilter && <Button variant="quiet" type="button" onClick={() => { setActorInput(''); setActorFilter(''); setOffset(0) }}>Clear</Button>}
        </form>
        {events.isLoading ? <Loading label="Loading audit events" /> : events.isError ? (
          <Alert>{events.error instanceof ApiError ? events.error.message : 'Audit events could not be loaded. Confirm this profile has auditor or administrator access.'}</Alert>
        ) : (events.data ?? []).length === 0 ? (
          <EmptyState title="No audit events returned" description="Only events returned by LedgerLine are shown here." />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Event</th><th>Actor</th><th>Transaction reference</th><th>Outcome</th><th>Date & time</th><th>Details</th></tr></thead>
              <tbody>
                {(events.data ?? []).map((event) => (
                  <tr key={event.id}>
                    <td><div className="audit-event-name"><span className={`audit-dot audit-${event.outcome.toLowerCase()}`} /><strong>{event.event_type.replaceAll('_', ' ')}</strong></div></td>
                    <td className="mono muted-cell">{event.actor_user_id ?? 'Unauthenticated'}</td>
                    <td className="mono muted-cell">{event.journal_transaction_id ?? '—'}</td>
                    <td><StatusPill status={event.outcome} /></td>
                    <td className="date-cell">{new Date(event.created_at).toLocaleString('en-IN')}</td>
                    <td>
                      <details className="audit-details">
                        <summary>View</summary>
                        <pre>{JSON.stringify(event.details, null, 2)}</pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="pagination">
          <span>{events.data?.length ?? 0} events in this page</span>
          <div>
            <Button variant="secondary" disabled={offset === 0 || events.isLoading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</Button>
            <Button variant="secondary" disabled={(events.data?.length ?? 0) < pageSize || events.isLoading} onClick={() => setOffset(offset + pageSize)}>Next</Button>
          </div>
        </div>
      </Card>
      <p className="page-footnote">Audit event details are intentionally not expanded here; the API records may contain operational metadata.</p>
    </>
  )
}
