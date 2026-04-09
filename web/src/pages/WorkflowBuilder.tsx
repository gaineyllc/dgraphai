// @ts-nocheck
/**
 * WorkflowBuilder — visual drag-and-drop workflow canvas.
 *
 * Built on React Flow. Users compose workflows by:
 *   1. Dragging step types from the left palette onto the canvas
 *   2. Connecting steps by drawing edges between handles
 *   3. Clicking a step to configure it in the right panel
 *   4. Saving and running the workflow
 *
 * Step types:
 *   trigger   — what starts the workflow (manual, query result, schedule)
 *   approval  — wait for human approval
 *   action    — execute a filesystem action (move/delete/tag)
 *   notify    — send a notification (Slack/email/webhook)
 *   condition — branch based on expression
 */
import { useState, useCallback, useRef } from 'react'
import ReactFlow, {
  ReactFlowProvider,
  addEdge,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
  BackgroundVariant,
  Panel,
  MiniMap,
  Handle,
  Position,
  NodeToolbar,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  Play, Save, Plus, Trash2, Settings, ChevronRight,
  Zap, UserCheck, Cpu, Bell, GitBranch, Clock,
  X, CheckCircle, AlertTriangle, Webhook
} from 'lucide-react'
import './WorkflowBuilder.css'

// ── Step type definitions ─────────────────────────────────────────────────────

const STEP_PALETTE = [
  {
    group: 'Triggers',
    items: [
      { type: 'trigger_manual',    label: 'Manual',        icon: Play,       color: '#4f8ef7', desc: 'Start on demand' },
      { type: 'trigger_query',     label: 'Query Result',  icon: Zap,        color: '#8b5cf6', desc: 'When query returns rows' },
      { type: 'trigger_schedule',  label: 'Schedule',      icon: Clock,      color: '#6366f1', desc: 'On a cron schedule' },
    ],
  },
  {
    group: 'Steps',
    items: [
      { type: 'approval',   label: 'Approval',   icon: UserCheck,    color: '#f59e0b', desc: 'Wait for human sign-off' },
      { type: 'action',     label: 'Action',     icon: Cpu,          color: '#10b981', desc: 'Move, delete, tag files' },
      { type: 'notify',     label: 'Notify',     icon: Bell,         color: '#06b6d4', desc: 'Slack, email, webhook' },
      { type: 'condition',  label: 'Condition',  icon: GitBranch,    color: '#f97316', desc: 'Branch on expression' },
    ],
  },
]

const STEP_META: Record<string, { color: string; icon: any; label: string }> = {}
STEP_PALETTE.forEach(g => g.items.forEach(i => { STEP_META[i.type] = i }))

// ── Custom node components ────────────────────────────────────────────────────

function StepNode({ data, selected }: any) {
  const meta  = STEP_META[data.stepType] ?? { color: '#6b7280', icon: Cpu, label: data.stepType }
  const Icon  = meta.icon
  const isTrigger = data.stepType?.startsWith('trigger')

  return (
    <div className={`wf-node ${selected ? 'wf-node-selected' : ''}`} style={{ '--node-color': meta.color } as any}>
      {!isTrigger && <Handle type="target" position={Position.Top} className="wf-handle wf-handle-top" />}

      <div className="wf-node-header">
        <div className="wf-node-icon" style={{ background: `${meta.color}20`, color: meta.color }}>
          <Icon size={14} />
        </div>
        <div className="wf-node-label-block">
          <div className="wf-node-type">{meta.label}</div>
          <div className="wf-node-name">{data.name || 'Untitled step'}</div>
        </div>
        {data.status === 'complete' && <CheckCircle size={14} className="wf-status-icon wf-status-ok" />}
        {data.status === 'error'    && <AlertTriangle size={14} className="wf-status-icon wf-status-err" />}
      </div>

      {data.description && (
        <div className="wf-node-desc">{data.description}</div>
      )}

      <Handle type="source" position={Position.Bottom} className="wf-handle wf-handle-bottom" />
      {data.stepType === 'condition' && (
        <Handle type="source" position={Position.Right} id="else" className="wf-handle wf-handle-right" />
      )}

      <NodeToolbar isVisible={selected} position={Position.Top}>
        <button className="wf-tool-btn wf-tool-delete" title="Delete step">
          <Trash2 size={12} />
        </button>
      </NodeToolbar>
    </div>
  )
}

const NODE_TYPES = { step: StepNode }

// ── Default starter workflow ──────────────────────────────────────────────────

const INITIAL_NODES = [
  {
    id: '1',
    type: 'step',
    position: { x: 250, y: 60 },
    data: {
      stepType: 'trigger_manual',
      name: 'Manual trigger',
      description: 'Start this workflow on demand',
    },
  },
  {
    id: '2',
    type: 'step',
    position: { x: 250, y: 200 },
    data: {
      stepType: 'approval',
      name: 'Approval gate',
      description: 'Security team must approve before proceeding',
    },
  },
  {
    id: '3',
    type: 'step',
    position: { x: 250, y: 340 },
    data: {
      stepType: 'action',
      name: 'Move files',
      description: 'Move selected files to archive',
    },
  },
  {
    id: '4',
    type: 'step',
    position: { x: 250, y: 480 },
    data: {
      stepType: 'notify',
      name: 'Notify team',
      description: 'Send Slack message on completion',
    },
  },
]

const INITIAL_EDGES = [
  { id: 'e1-2', source: '1', target: '2', animated: true, style: { stroke: '#4f8ef7', strokeWidth: 2 } },
  { id: 'e2-3', source: '2', target: '3', animated: false, style: { stroke: '#252535', strokeWidth: 2 } },
  { id: 'e3-4', source: '3', target: '4', animated: false, style: { stroke: '#252535', strokeWidth: 2 } },
]

// ── WorkflowBuilder ───────────────────────────────────────────────────────────

export function WorkflowBuilder() {
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES)
  const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES)
  const [selectedNode, setSelectedNode]  = useState(null)
  const [workflowName, setWorkflowName]  = useState('New workflow')
  const [isDragging, setIsDragging]      = useState(false)
  const reactFlowWrapper                 = useRef(null)
  const [reactFlowInstance, setRFI]      = useState(null)
  let nodeId = useRef(100)

  const onConnect = useCallback((params) => {
    setEdges(eds => addEdge({
      ...params,
      animated: false,
      style: { stroke: '#252535', strokeWidth: 2 },
    }, eds))
  }, [setEdges])

  const onNodeClick = useCallback((_e, node) => {
    setSelectedNode(node)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
  }, [])

  // Drag from palette → drop onto canvas
  const onDragStart = (e, stepType) => {
    e.dataTransfer.setData('application/reactflow', stepType)
    e.dataTransfer.effectAllowed = 'move'
    setIsDragging(true)
  }

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const stepType = e.dataTransfer.getData('application/reactflow')
    if (!stepType || !reactFlowInstance) return

    const bounds  = reactFlowWrapper.current.getBoundingClientRect()
    const position = reactFlowInstance.screenToFlowPosition({
      x: e.clientX - bounds.left,
      y: e.clientY - bounds.top,
    })

    const meta = STEP_META[stepType] ?? { label: stepType }
    const id   = String(++nodeId.current)

    setNodes(nds => nds.concat({
      id,
      type:     'step',
      position,
      data: {
        stepType,
        name:        `New ${meta.label.toLowerCase()}`,
        description: '',
      },
    }))
  }, [reactFlowInstance, setNodes])

  const onDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const deleteSelected = useCallback(() => {
    if (!selectedNode) return
    setNodes(nds => nds.filter(n => n.id !== selectedNode.id))
    setEdges(eds => eds.filter(e => e.source !== selectedNode.id && e.target !== selectedNode.id))
    setSelectedNode(null)
  }, [selectedNode, setNodes, setEdges])

  const updateNodeData = useCallback((field, value) => {
    if (!selectedNode) return
    setNodes(nds => nds.map(n =>
      n.id === selectedNode.id
        ? { ...n, data: { ...n.data, [field]: value } }
        : n
    ))
    setSelectedNode(sn => sn ? { ...sn, data: { ...sn.data, [field]: value } } : sn)
  }, [selectedNode, setNodes])

  const saveWorkflow = async () => {
    const steps = nodes.map((n, i) => ({
      id:     n.id,
      type:   n.data.stepType,
      name:   n.data.name,
      config: n.data.config ?? {},
      position_x: n.position.x,
      position_y: n.position.y,
    }))
    try {
      await fetch('/api/workflows/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: workflowName, steps, trigger_type: 'manual' }),
      })
      alert('Workflow saved!')
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="workflow-builder">
      {/* Top bar */}
      <div className="wb-topbar">
        <input
          value={workflowName}
          onChange={e => setWorkflowName(e.target.value)}
          className="wb-name-input"
          placeholder="Workflow name"
        />
        <div className="wb-topbar-actions">
          <button className="wb-btn wb-btn-ghost" onClick={deleteSelected} disabled={!selectedNode}>
            <Trash2 size={13} /> Delete step
          </button>
          <button className="wb-btn wb-btn-primary" onClick={saveWorkflow}>
            <Save size={13} /> Save
          </button>
          <button className="wb-btn wb-btn-success">
            <Play size={13} /> Run
          </button>
        </div>
      </div>

      <div className="wb-body">
        {/* Step palette */}
        <div className="wb-palette">
          <div className="wb-palette-title">Steps</div>
          <div className="wb-palette-hint">Drag onto canvas</div>
          {STEP_PALETTE.map(group => (
            <div key={group.group} className="wb-palette-group">
              <div className="wb-palette-group-label">{group.group}</div>
              {group.items.map(item => {
                const Icon = item.icon
                return (
                  <div
                    key={item.type}
                    className="wb-palette-item"
                    draggable
                    onDragStart={e => onDragStart(e, item.type)}
                    title={item.desc}
                  >
                    <div className="wb-pi-icon" style={{ background: `${item.color}20`, color: item.color }}>
                      <Icon size={13} />
                    </div>
                    <div>
                      <div className="wb-pi-label">{item.label}</div>
                      <div className="wb-pi-desc">{item.desc}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        {/* Canvas */}
        <div ref={reactFlowWrapper} className={`wb-canvas ${isDragging ? 'wb-canvas-dragging' : ''}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onInit={setRFI}
            nodeTypes={NODE_TYPES}
            fitView
            proOptions={{ hideAttribution: true }}
            style={{ background: '#0a0a0f' }}
            defaultEdgeOptions={{
              style: { stroke: '#252535', strokeWidth: 2 },
              animated: false,
            }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1}
              color="#1e1e2e"
            />
            <Controls
              style={{
                background: '#12121a',
                border: '1px solid #252535',
                borderRadius: 8,
              }}
            />
            <MiniMap
              style={{ background: '#12121a', border: '1px solid #252535' }}
              nodeColor={n => STEP_META[n.data?.stepType]?.color ?? '#6b7280'}
              maskColor="rgba(0,0,0,0.6)"
            />
            <Panel position="top-right">
              <div className="wb-canvas-hint">
                Connect steps by dragging from ● to ●
              </div>
            </Panel>
          </ReactFlow>
        </div>

        {/* Config panel */}
        {selectedNode && (
          <StepConfigPanel
            node={selectedNode}
            onUpdate={updateNodeData}
            onClose={() => setSelectedNode(null)}
            onDelete={deleteSelected}
          />
        )}
      </div>
    </div>
  )
}

// ── Step config panel ──────────────────────────────────────────────────────────

function StepConfigPanel({ node, onUpdate, onClose, onDelete }) {
  const meta  = STEP_META[node.data.stepType] ?? { color: '#6b7280', label: node.data.stepType }
  const Icon  = meta.icon ?? Cpu

  return (
    <div className="wb-config-panel">
      <div className="wb-cp-header">
        <div className="wb-cp-icon" style={{ background: `${meta.color}20`, color: meta.color }}>
          <Icon size={14} />
        </div>
        <div>
          <div className="wb-cp-type">{meta.label}</div>
          <div className="wb-cp-id">Step ID: {node.id}</div>
        </div>
        <button onClick={onClose} className="wb-cp-close"><X size={14} /></button>
      </div>

      <div className="wb-cp-body">
        <div className="wb-cp-field">
          <label>Step name</label>
          <input
            value={node.data.name || ''}
            onChange={e => onUpdate('name', e.target.value)}
            placeholder="Name this step"
          />
        </div>

        <div className="wb-cp-field">
          <label>Description</label>
          <textarea
            value={node.data.description || ''}
            onChange={e => onUpdate('description', e.target.value)}
            placeholder="What does this step do?"
            rows={2}
          />
        </div>

        {/* Type-specific config */}
        {node.data.stepType === 'approval' && <ApprovalConfig node={node} onUpdate={onUpdate} />}
        {node.data.stepType === 'action'   && <ActionConfig   node={node} onUpdate={onUpdate} />}
        {node.data.stepType === 'notify'   && <NotifyConfig   node={node} onUpdate={onUpdate} />}
        {node.data.stepType === 'condition'&& <ConditionConfig node={node} onUpdate={onUpdate} />}
        {node.data.stepType?.startsWith('trigger') && <TriggerConfig node={node} onUpdate={onUpdate} />}
      </div>

      <div className="wb-cp-footer">
        <button onClick={onDelete} className="wb-cp-delete">
          <Trash2 size={12} /> Remove step
        </button>
      </div>
    </div>
  )
}

function ApprovalConfig({ node, onUpdate }) {
  const cfg = node.data.config ?? {}
  return (
    <div className="wb-type-config">
      <div className="wb-cp-field">
        <label>Timeout (hours)</label>
        <input
          type="number" min={1} max={720}
          value={cfg.timeout_hours ?? 48}
          onChange={e => onUpdate('config', { ...cfg, timeout_hours: Number(e.target.value) })}
        />
      </div>
      <div className="wb-cp-field">
        <label>Require any approver</label>
        <select
          value={String(cfg.any_of ?? true)}
          onChange={e => onUpdate('config', { ...cfg, any_of: e.target.value === 'true' })}
        >
          <option value="true">Any approver is enough</option>
          <option value="false">All approvers required</option>
        </select>
      </div>
    </div>
  )
}

function ActionConfig({ node, onUpdate }) {
  const cfg = node.data.config ?? {}
  return (
    <div className="wb-type-config">
      <div className="wb-cp-field">
        <label>Action type</label>
        <select
          value={cfg.action_type ?? 'move'}
          onChange={e => onUpdate('config', { ...cfg, action_type: e.target.value })}
        >
          <option value="move">Move files</option>
          <option value="delete">Delete files</option>
          <option value="tag">Add tags</option>
          <option value="rename">Rename</option>
        </select>
      </div>
      {cfg.action_type === 'move' && (
        <div className="wb-cp-field">
          <label>Destination</label>
          <input
            value={cfg.destination ?? ''}
            onChange={e => onUpdate('config', { ...cfg, destination: e.target.value })}
            placeholder="e.g. smb://nas/Media/Archive"
          />
        </div>
      )}
      <div className="wb-cp-field wb-cp-toggle">
        <label>Dry run (preview only)</label>
        <input
          type="checkbox"
          checked={cfg.dry_run !== false}
          onChange={e => onUpdate('config', { ...cfg, dry_run: e.target.checked })}
        />
      </div>
    </div>
  )
}

function NotifyConfig({ node, onUpdate }) {
  const cfg = node.data.config ?? {}
  return (
    <div className="wb-type-config">
      <div className="wb-cp-field">
        <label>Channel</label>
        <select
          value={cfg.channel ?? 'slack'}
          onChange={e => onUpdate('config', { ...cfg, channel: e.target.value })}
        >
          <option value="slack">Slack</option>
          <option value="email">Email</option>
          <option value="webhook">Webhook</option>
          <option value="pagerduty">PagerDuty</option>
        </select>
      </div>
      <div className="wb-cp-field">
        <label>{cfg.channel === 'slack' ? 'Webhook URL' : cfg.channel === 'email' ? 'To address' : 'URL'}</label>
        <input
          value={cfg.target ?? ''}
          onChange={e => onUpdate('config', { ...cfg, target: e.target.value })}
          placeholder={cfg.channel === 'email' ? 'security@company.com' : 'https://...'}
        />
      </div>
      <div className="wb-cp-field">
        <label>Message template</label>
        <textarea
          value={cfg.message ?? ''}
          onChange={e => onUpdate('config', { ...cfg, message: e.target.value })}
          placeholder="{{file_count}} files processed in workflow {{run_id}}"
          rows={2}
        />
        <div className="wb-cp-hint">Variables: {'{{file_count}} {{run_id}} {{step_name}}'}</div>
      </div>
    </div>
  )
}

function ConditionConfig({ node, onUpdate }) {
  const cfg = node.data.config ?? {}
  return (
    <div className="wb-type-config">
      <div className="wb-cp-field">
        <label>Expression</label>
        <input
          value={cfg.expression ?? ''}
          onChange={e => onUpdate('config', { ...cfg, expression: e.target.value })}
          placeholder="file_count > 10"
        />
        <div className="wb-cp-hint">Variables: file_count, approval_count, error_count</div>
      </div>
      <div className="wb-cp-hint-box">
        The <strong>bottom handle</strong> is the "true" branch.<br/>
        The <strong>right handle</strong> is the "false" (else) branch.
      </div>
    </div>
  )
}

function TriggerConfig({ node, onUpdate }) {
  const cfg = node.data.config ?? {}
  const isSchedule = node.data.stepType === 'trigger_schedule'
  const isQuery    = node.data.stepType === 'trigger_query'
  return (
    <div className="wb-type-config">
      {isSchedule && (
        <div className="wb-cp-field">
          <label>Cron expression</label>
          <input
            value={cfg.cron ?? '0 9 * * 1'}
            onChange={e => onUpdate('config', { ...cfg, cron: e.target.value })}
            placeholder="0 9 * * 1  (Monday 9am)"
          />
          <div className="wb-cp-hint">Standard cron format. Uses UTC.</div>
        </div>
      )}
      {isQuery && (
        <div className="wb-cp-field">
          <label>Saved query</label>
          <input
            value={cfg.query_id ?? ''}
            onChange={e => onUpdate('config', { ...cfg, query_id: e.target.value })}
            placeholder="Query ID from Graph Control"
          />
          <div className="wb-cp-hint">Workflow runs when query returns &gt; 0 rows</div>
        </div>
      )}
    </div>
  )
}

// Wrap in provider
export default function WorkflowBuilderPage() {
  return (
    <ReactFlowProvider>
      <WorkflowBuilder />
    </ReactFlowProvider>
  )
}
