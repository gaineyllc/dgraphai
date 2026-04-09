/**
 * MountsPage — add and manage filesystem sources.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, CheckCircle, XCircle, Clock, HardDrive } from 'lucide-react'
import { mountsApi, indexerApi, type Mount } from '../lib/api'

export function MountsPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', uri: '', auto_index: true })
  const [formError, setFormError] = useState<string | null>(null)

  const { data: mounts = [], isLoading } = useQuery({
    queryKey: ['mounts'],
    queryFn: mountsApi.list,
    refetchInterval: 10_000,
  })

  const addMount = useMutation({
    mutationFn: () => mountsApi.add(form.name, form.uri, form.auto_index),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mounts'] })
      setShowAdd(false)
      setForm({ name: '', uri: '', auto_index: true })
      setFormError(null)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const removeMount = useMutation({
    mutationFn: mountsApi.remove,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mounts'] }),
  })

  const startIndex = useMutation({
    mutationFn: (mount_id: string) => indexerApi.start(mount_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['mounts'] }),
  })

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-[#e2e2f0]">Filesystem Sources</h1>
            <p className="text-sm text-[#55557a] mt-1">
              Add local paths, SMB shares, or NFS exports to index into the graph.
            </p>
          </div>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-3 py-2 bg-[#4f8ef7] text-white text-sm font-medium rounded-lg hover:bg-[#3a7de6] transition-colors"
          >
            <Plus size={14} />
            Add source
          </button>
        </div>

        {/* Add form */}
        {showAdd && (
          <div className="mb-4 p-4 bg-[#12121a] border border-[#252535] rounded-xl">
            <h3 className="text-sm font-medium text-[#e2e2f0] mb-3">New filesystem source</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-[#55557a] mb-1 block">Name</label>
                <input
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="My NAS Media"
                  className="w-full px-3 py-2 text-sm bg-[#0a0a0f] border border-[#252535] rounded-lg text-[#e2e2f0] focus:outline-none focus:border-[#4f8ef7] placeholder-[#55557a]"
                />
              </div>
              <div>
                <label className="text-xs text-[#55557a] mb-1 block">URI</label>
                <input
                  value={form.uri}
                  onChange={e => setForm(f => ({ ...f, uri: e.target.value }))}
                  placeholder="smb://user:pass@192.168.1.x/Media  or  /mnt/nas  or  C:\Users\..."
                  className="w-full px-3 py-2 text-sm bg-[#0a0a0f] border border-[#252535] rounded-lg text-[#e2e2f0] focus:outline-none focus:border-[#4f8ef7] placeholder-[#55557a] font-mono"
                />
              </div>
              {formError && (
                <p className="text-xs text-[#f87171]">{formError}</p>
              )}
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setShowAdd(false); setFormError(null) }}
                  className="px-3 py-1.5 text-sm text-[#8888aa] hover:text-[#e2e2f0] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => addMount.mutate()}
                  disabled={!form.name || !form.uri || addMount.isPending}
                  className="px-4 py-1.5 text-sm bg-[#4f8ef7] text-white rounded-lg hover:bg-[#3a7de6] disabled:opacity-50 transition-colors"
                >
                  {addMount.isPending ? 'Adding…' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Mount list */}
        {isLoading ? (
          <div className="text-center text-[#55557a] py-12">Loading…</div>
        ) : mounts.length === 0 ? (
          <div className="text-center py-12">
            <HardDrive size={32} className="mx-auto text-[#252535] mb-3" />
            <div className="text-[#55557a]">No sources configured</div>
            <div className="text-sm text-[#55557a] mt-1">Add a filesystem source to start indexing</div>
          </div>
        ) : (
          <div className="space-y-2">
            {mounts.map(mount => (
              <MountCard
                key={mount.id}
                mount={mount}
                onRemove={() => removeMount.mutate(mount.id)}
                onIndex={() => startIndex.mutate(mount.id)}
                indexing={startIndex.isPending}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function MountCard({ mount, onRemove, onIndex, indexing }: {
  mount: Mount
  onRemove: () => void
  onIndex: () => void
  indexing: boolean
}) {
  const statusIcon = mount.reachable
    ? <CheckCircle size={14} className="text-[#34d399]" />
    : <XCircle size={14} className="text-[#f87171]" />

  const indexBadge = {
    never:    <span className="text-[#55557a]">Never indexed</span>,
    complete: <span className="text-[#34d399]">{mount.file_count.toLocaleString()} files</span>,
    running:  <span className="text-[#fbbf24]">Indexing…</span>,
    error:    <span className="text-[#f87171]">Error</span>,
  }[mount.index_status] ?? <span className="text-[#55557a]">{mount.index_status}</span>

  return (
    <div className="flex items-center gap-4 p-4 bg-[#12121a] border border-[#252535] rounded-xl hover:border-[#352535] transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {statusIcon}
          <span className="font-medium text-[#e2e2f0]">{mount.name}</span>
          <span className="text-xs text-[#55557a] capitalize bg-[#1a1a28] px-1.5 py-0.5 rounded">{mount.protocol}</span>
        </div>
        <div className="text-xs text-[#55557a] font-mono truncate">{mount.uri}</div>
        <div className="text-xs mt-1 flex items-center gap-1">
          <Clock size={10} className="text-[#55557a]" />
          {indexBadge}
          {mount.last_indexed && (
            <span className="text-[#55557a]">
              · {new Date(mount.last_indexed).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={onIndex}
          disabled={indexing || !mount.reachable}
          title="Start indexing"
          className="w-8 h-8 flex items-center justify-center text-[#55557a] hover:text-[#4f8ef7] disabled:opacity-30 transition-colors"
        >
          <RefreshCw size={14} className={indexing ? 'animate-spin' : ''} />
        </button>
        <button
          onClick={onRemove}
          title="Remove source"
          className="w-8 h-8 flex items-center justify-center text-[#55557a] hover:text-[#f87171] transition-colors"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  )
}
