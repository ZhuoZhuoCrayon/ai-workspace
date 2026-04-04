import { useEffect, useMemo, useState } from 'react'

import Fuse from 'fuse.js'
import rehypeHighlight from 'rehype-highlight'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { KnowledgeDoc, KnowledgePayload, Visibility } from './types'

import 'highlight.js/styles/github.css'
import './App.css'

const DATA_URL = `${import.meta.env.BASE_URL}data/knowledge.json`

function formatDate(dateStr: string): string {
  if (!dateStr) return '未知'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return dateStr
  return date.toISOString().slice(0, 10)
}

function displayVisibility(visibility: Visibility): string {
  return visibility === 'public' ? '公开' : '私有'
}

function App() {
  const [payload, setPayload] = useState<KnowledgePayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [selectedProject, setSelectedProject] = useState('all')
  const [selectedVisibility, setSelectedVisibility] = useState<'all' | Visibility>('all')
  const [selectedDocId, setSelectedDocId] = useState('')

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true)
        const response = await fetch(DATA_URL)
        if (!response.ok) {
          throw new Error(`请求失败：${response.status}`)
        }
        const data = (await response.json()) as KnowledgePayload
        setPayload(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setLoading(false)
      }
    }

    void loadData()
  }, [])

  const docs = useMemo(() => payload?.docs ?? [], [payload])

  const filteredByScope = useMemo(() => {
    return docs.filter((doc) => {
      const projectHit = selectedProject === 'all' || doc.project === selectedProject
      const visibilityHit = selectedVisibility === 'all' || doc.visibility === selectedVisibility
      return projectHit && visibilityHit
    })
  }, [docs, selectedProject, selectedVisibility])

  const fuse = useMemo(() => {
    return new Fuse(filteredByScope, {
      keys: ['title', 'description', 'tags', 'project', 'plain_text'],
      threshold: 0.34,
      ignoreLocation: true,
      minMatchCharLength: 2,
    })
  }, [filteredByScope])

  const filteredDocs = useMemo(() => {
    if (!query.trim()) return filteredByScope
    return fuse.search(query.trim()).map((item) => item.item)
  }, [fuse, filteredByScope, query])

  useEffect(() => {
    if (filteredDocs.length === 0) {
      setSelectedDocId('')
      return
    }
    const exists = filteredDocs.some((doc) => doc.id === selectedDocId)
    if (!exists) {
      setSelectedDocId(filteredDocs[0].id)
    }
  }, [filteredDocs, selectedDocId])

  const selectedDoc = useMemo(() => {
    return filteredDocs.find((doc) => doc.id === selectedDocId) ?? null
  }, [filteredDocs, selectedDocId])

  const projectOptions = useMemo(() => {
    const grouped = new Map<string, number>()
    for (const doc of docs) {
      const key = doc.project
      grouped.set(key, (grouped.get(key) ?? 0) + 1)
    }
    return [...grouped.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  }, [docs])

  const summary = payload?.stats

  if (loading) {
    return <div className="status-card">正在加载知识资产数据...</div>
  }

  if (error) {
    return <div className="status-card error">加载失败：{error}</div>
  }

  if (!payload) {
    return <div className="status-card error">未读取到数据。</div>
  }

  return (
    <div className="layout">
      <header className="topbar">
        <div>
          <p className="badge">AI Workspace Knowledge</p>
          <h1>知识资产可视化</h1>
          <p className="subtitle">
            基于 INDEX 遍历发现文档，支持关键字、项目和可见性过滤。
          </p>
        </div>
        <div className="stats-grid">
          <div>
            <span>文档</span>
            <strong>{summary?.docs_count ?? 0}</strong>
          </div>
          <div>
            <span>项目</span>
            <strong>{summary?.projects_count ?? 0}</strong>
          </div>
          <div>
            <span>仓库</span>
            <strong>{summary?.repos_count ?? 0}</strong>
          </div>
        </div>
      </header>

      <section className="toolbar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="按关键字、标题、标签、正文检索..."
        />
        <div className="segmented">
          {(['all', 'public', 'private'] as const).map((value) => (
            <button
              key={value}
              className={value === selectedVisibility ? 'active' : ''}
              onClick={() => setSelectedVisibility(value)}
            >
              {value === 'all' ? '全部' : displayVisibility(value)}
            </button>
          ))}
        </div>
      </section>

      <main className="content-grid">
        <aside className="panel projects">
          <h2>项目</h2>
          <button
            className={selectedProject === 'all' ? 'project-item active' : 'project-item'}
            onClick={() => setSelectedProject('all')}
          >
            <span>全部项目</span>
            <em>{docs.length}</em>
          </button>
          {projectOptions.map((project) => (
            <button
              key={project.name}
              className={selectedProject === project.name ? 'project-item active' : 'project-item'}
              onClick={() => setSelectedProject(project.name)}
            >
              <span>{project.name}</span>
              <em>{project.count}</em>
            </button>
          ))}
        </aside>

        <section className="panel doc-list">
          <div className="panel-head">
            <h2>文档</h2>
            <span>{filteredDocs.length} 条</span>
          </div>
          <div className="scroll-area">
            {filteredDocs.map((doc) => (
              <article
                key={doc.id}
                className={doc.id === selectedDocId ? 'doc-item active' : 'doc-item'}
                onClick={() => setSelectedDocId(doc.id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') setSelectedDocId(doc.id)
                }}
                role="button"
                tabIndex={0}
              >
                <h3>{doc.title}</h3>
                <p className="doc-meta">
                  {doc.project} · {displayVisibility(doc.visibility)} · {formatDate(doc.updated || doc.created)}
                </p>
                <p className="doc-excerpt">{doc.description || doc.excerpt || '暂无摘要'}</p>
                <p className="doc-path">{doc.path}</p>
              </article>
            ))}
            {filteredDocs.length === 0 ? <p className="empty">未命中结果，请调整搜索条件。</p> : null}
          </div>
        </section>

        <section className="panel reader">
          {selectedDoc ? <Reader doc={selectedDoc} /> : <p className="empty">请选择一篇文档开始阅读。</p>}
        </section>
      </main>

      <footer className="footer">
        数据生成时间：{formatDate(payload.generated_at)} · 警告：{payload.warnings.length}
      </footer>
    </div>
  )
}

function Reader({ doc }: { doc: KnowledgeDoc }) {
  return (
    <>
      <div className="panel-head">
        <div>
          <h2>{doc.title}</h2>
          <p className="doc-meta">
            {doc.project} · {displayVisibility(doc.visibility)} · {formatDate(doc.updated || doc.created)}
          </p>
        </div>
        <div className="tag-wrap">
          {doc.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="tag">
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div className="scroll-area markdown-wrap">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {doc.content}
        </ReactMarkdown>
      </div>
    </>
  )
}

export default App
