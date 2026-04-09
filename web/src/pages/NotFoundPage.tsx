// @ts-nocheck
import { useNavigate } from 'react-router-dom'
import { Network } from 'lucide-react'

export function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', background: '#0a0a0f', gap: 16,
    }}>
      <div style={{
        width: 64, height: 64, borderRadius: 16, background: '#12121a',
        border: '1px solid #252535', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Network size={28} style={{ color: '#252535' }} />
      </div>
      <h1 style={{ fontSize: 48, fontWeight: 800, color: '#252535', margin: 0 }}>404</h1>
      <p style={{ fontSize: 14, color: '#55557a', margin: 0 }}>This page doesn't exist in the graph.</p>
      <button
        onClick={() => navigate('/')}
        style={{
          padding: '10px 20px', borderRadius: 9, border: 'none',
          background: '#4f8ef7', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer',
        }}>
        Back to Graph Explorer
      </button>
    </div>
  )
}
