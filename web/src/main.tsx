import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// ── Theme initialization — runs before React mounts to avoid FOUC ─────────────
;(() => {
  const stored = localStorage.getItem('dgraph-theme')
  const system  = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  const theme   = stored ?? system
  document.documentElement.setAttribute('data-theme', theme)
})()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
