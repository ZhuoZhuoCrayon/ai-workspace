import fs from 'node:fs'
import path from 'node:path'

import matter from 'gray-matter'
import yaml from 'js-yaml'

const APP_ROOT = path.resolve(import.meta.dirname, '..')
const WORKSPACE_ROOT = path.resolve(APP_ROOT, '..', '..')
const DOCS_DIR = path.join(APP_ROOT, 'docs')
const VITEPRESS_DIR = path.join(DOCS_DIR, '.vitepress')
const SIDEBAR_OUTPUT = path.join(VITEPRESS_DIR, 'sidebar.generated.json')
const META_OUTPUT = path.join(VITEPRESS_DIR, 'meta.generated.json')
const KNOWLEDGE_DEST = path.join(DOCS_DIR, 'knowledge')

const REPO_SOURCES = [
  { file: 'repos.json', visibility: 'public', format: 'json' },
  { file: 'private/repos.json', visibility: 'private', format: 'json' },
  { file: 'repos.yaml', visibility: 'public', format: 'yaml' },
  { file: 'private/repos.yaml', visibility: 'private', format: 'yaml' },
]

const INDEX_ROOTS = ['knowledge/INDEX.md', 'private/knowledge/INDEX.md']

// ── helpers ──

function safeRead(filePath) {
  try {
    return fs.readFileSync(filePath, 'utf-8')
  } catch {
    return null
  }
}

function parseRegistryFile(filePath, format) {
  const raw = safeRead(filePath)
  if (!raw) return []
  const parsed = format === 'yaml' ? yaml.load(raw) : JSON.parse(raw)
  return Array.isArray(parsed) ? parsed : []
}

function normalizeRelPath(absPath) {
  return path.relative(WORKSPACE_ROOT, absPath).split(path.sep).join('/')
}

function isKnowledgePath(relPath) {
  return relPath.startsWith('knowledge/') || relPath.startsWith('private/knowledge/')
}

function parseProject(relPath) {
  const parts = relPath.split('/')
  if (parts[0] === 'knowledge') {
    const proj = parts[1] ?? '_unknown'
    if (proj.toLowerCase().endsWith('.md')) return { visibility: 'public', project: '_root' }
    return { visibility: 'public', project: proj }
  }
  const proj = parts[2] ?? '_unknown'
  if (proj.toLowerCase().endsWith('.md')) return { visibility: 'private', project: '_root' }
  return { visibility: 'private', project: proj }
}

function extractLinks(markdown) {
  const links = []
  const re = /\[[^\]]+\]\(([^)]+)\)/g
  let m
  while ((m = re.exec(markdown))) links.push(m[1])
  return links
}

function pickTitle(data, content, fallback) {
  if (typeof data.title === 'string' && data.title.trim()) return data.title.trim()
  const h = content.match(/^#\s+(.+)$/m)
  return h?.[1]?.trim() || fallback
}

// ── repos ──

function collectRepos(warnings) {
  const repos = []
  for (const src of REPO_SOURCES) {
    const abs = path.join(WORKSPACE_ROOT, src.file)
    if (!fs.existsSync(abs)) continue
    try {
      for (const row of parseRegistryFile(abs, src.format)) {
        if (!row || typeof row !== 'object') continue
        repos.push({
          name: String(row.name ?? ''),
          description: String(row.description ?? ''),
          git_url: String(row.git_url ?? ''),
          branch: String(row.branch ?? ''),
          language: String(row.language ?? ''),
          visibility: src.visibility,
        })
      }
    } catch (e) {
      warnings.push(`仓库注册表解析失败：${src.file}（${e}）`)
    }
  }
  const uniq = new Map()
  for (const r of repos) {
    const k = `${r.visibility}:${r.name}`
    if (r.name && !uniq.has(k)) uniq.set(k, r)
  }
  return [...uniq.values()].sort((a, b) => a.name.localeCompare(b.name))
}

// ── BFS doc discovery ──

function discoverDocs(warnings) {
  const queue = INDEX_ROOTS.map((p) => path.join(WORKSPACE_ROOT, p)).filter((p) => fs.existsSync(p))
  const visited = new Set()
  const allPaths = new Set()

  while (queue.length) {
    const cur = queue.shift()
    if (!cur || visited.has(cur)) continue
    visited.add(cur)

    const raw = safeRead(cur)
    if (!raw) { warnings.push(`无法读取索引：${normalizeRelPath(cur)}`); continue }
    allPaths.add(cur)

    for (const link of extractLinks(raw)) {
      const clean = link.split('#')[0]?.trim()
      if (!clean || /^https?:\/\//i.test(clean) || clean.startsWith('mailto:') || !clean.endsWith('.md')) continue
      const target = path.resolve(path.dirname(cur), decodeURIComponent(clean))
      if (!target.startsWith(WORKSPACE_ROOT)) continue
      if (!fs.existsSync(target)) { warnings.push(`链接文件不存在：${normalizeRelPath(target)}`); continue }
      allPaths.add(target)
      const baseName = path.basename(target).toLowerCase()
      if (baseName === 'index.md' || baseName === 'readme.md') queue.push(target)
    }
  }
  return [...allPaths].filter((p) => isKnowledgePath(normalizeRelPath(p))).sort()
}

// ── frontmatter sanitization & copy ──

function safeParseFrontmatter(raw) {
  try {
    const { data, content } = matter(raw)
    if (data && typeof data === 'object' && Object.keys(data).length > 0) {
      return { data, content }
    }
  } catch { /* fall through */ }

  const lines = raw.split('\n')
  if (lines[0]?.trim() !== '---') return { data: {}, content: raw }

  const data = {}
  let endIdx = -1
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i]
    if (line.trim() === '---') { endIdx = i; break }
    if (line.trim() === '') continue
    if (/^##?\s/.test(line)) { endIdx = i; break }

    const colonIdx = line.indexOf(':')
    if (colonIdx > 0 && !/^##?\s/.test(line)) {
      const key = line.slice(0, colonIdx).trim()
      let val = line.slice(colonIdx + 1).trim()
      if (/^\[.*\]$/.test(val)) {
        try { val = JSON.parse(val.replace(/'/g, '"')) } catch { /* keep string */ }
      }
      if (/^\d{4}-\d{2}-\d{2}$/.test(val)) { /* keep as string */ }
      data[key] = val
    }
  }

  const content = endIdx >= 0 ? lines.slice(endIdx + (lines[endIdx]?.trim() === '---' ? 1 : 0)).join('\n') : lines.slice(1).join('\n')
  return { data, content }
}

function buildCleanMarkdown(data, content) {
  const fm = {}
  for (const key of ['title', 'description', 'tags', 'created', 'updated']) {
    if (data[key] !== undefined && data[key] !== '') fm[key] = data[key]
  }

  if (Object.keys(fm).length === 0) return content

  const yamlStr = Object.entries(fm)
    .map(([k, v]) => {
      if (Array.isArray(v)) return `${k}: [${v.map((i) => JSON.stringify(String(i))).join(', ')}]`
      return `${k}: ${JSON.stringify(String(v))}`
    })
    .join('\n')

  return `---\n${yamlStr}\n---\n${content}`
}

function copyKnowledgeDocs(docAbsPaths, warnings) {
  fs.rmSync(KNOWLEDGE_DEST, { recursive: true, force: true })

  const docs = []
  for (const absPath of docAbsPaths) {
    const relPath = normalizeRelPath(absPath)
    const knowledgeRel = relPath.startsWith('knowledge/') ? relPath.slice('knowledge/'.length) : relPath
    const destPath = path.join(KNOWLEDGE_DEST, knowledgeRel)

    const raw = safeRead(absPath)
    if (!raw) continue

    const { data, content } = safeParseFrontmatter(raw)
    const { project, visibility } = parseProject(relPath)
    const title = pickTitle(data, content, path.basename(relPath, '.md'))

    const cleanMd = buildCleanMarkdown(data, content)

    fs.mkdirSync(path.dirname(destPath), { recursive: true })
    fs.writeFileSync(destPath, cleanMd, 'utf-8')

    docs.push({
      path: `knowledge/${knowledgeRel}`,
      title,
      description: typeof data.description === 'string' ? data.description : '',
      tags: Array.isArray(data.tags) ? data.tags.map(String) : [],
      created: String(data.created ?? ''),
      updated: String(data.updated ?? ''),
      project,
      visibility,
    })
  }
  return docs
}

// ── sidebar ──

function buildSidebar(docs) {
  const byProject = new Map()
  for (const doc of docs) {
    if (!byProject.has(doc.project)) byProject.set(doc.project, [])
    byProject.get(doc.project).push(doc)
  }

  const sidebar = {}
  for (const [project, pDocs] of [...byProject.entries()].filter(([p]) => p !== '_root').sort((a, b) => a[0].localeCompare(b[0]))) {
    const prefix = `/knowledge/${project}/`
    const byKind = new Map()

    for (const doc of pDocs) {
      const rel = doc.path.replace(`knowledge/${project}/`, '')
      const parts = rel.split('/')
      const kind = parts.length > 1 ? parts[0] : '_root'
      if (!byKind.has(kind)) byKind.set(kind, [])
      byKind.get(kind).push(doc)
    }

    const groups = []
    for (const [kind, kDocs] of [...byKind.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const items = kDocs
        .sort((a, b) => {
          const tA = Date.parse(b.updated || b.created || '') || 0
          const tB = Date.parse(a.updated || a.created || '') || 0
          return tA - tB || a.title.localeCompare(b.title)
        })
        .map((d) => ({ text: d.title, link: `/${d.path}` }))

      if (kind === '_root') {
        groups.unshift({ text: project, items })
      } else {
        groups.push({ text: kind, collapsed: kind !== 'issues', items })
      }
    }
    sidebar[prefix] = groups
  }
  return sidebar
}

// ── meta & pages ──

function buildTagIndex(docs) {
  const m = new Map()
  for (const d of docs) for (const t of d.tags) {
    if (!m.has(t)) m.set(t, [])
    m.get(t).push({ title: d.title, path: d.path, project: d.project })
  }
  return Object.fromEntries([...m.entries()].sort((a, b) => b[1].length - a[1].length))
}

function buildCalendar(docs) {
  const m = new Map()
  for (const d of docs) {
    const date = (d.updated || d.created || '').slice(0, 10)
    if (date.length === 10) m.set(date, (m.get(date) ?? 0) + 1)
  }
  return Object.fromEntries([...m.entries()].sort())
}

function writeTagsPage(tags) {
  const lines = ['---', 'title: 标签索引', 'sidebar: false', '---', '', '# 标签索引', '']
  for (const [tag, tagDocs] of Object.entries(tags)) {
    lines.push(`## ${tag}`, '')
    for (const d of tagDocs) lines.push(`- [${d.title}](/${d.path}) <small>${d.project}</small>`)
    lines.push('')
  }
  fs.writeFileSync(path.join(DOCS_DIR, 'tags.md'), lines.join('\n'), 'utf-8')
}

function writeProjectsPage(projects, repos) {
  const lines = [
    '---', 'title: 项目概览', 'sidebar: false', '---', '', '# 项目概览', '',
    '| 项目 | 文档数 | 描述 |', '|------|--------|------|',
  ]
  for (const p of projects) {
    const r = repos.find((r) => r.name === p.project)
    lines.push(`| [${p.project}](/knowledge/${p.project}/INDEX) | ${p.docs_count} | ${r?.description || ''} |`)
  }
  lines.push('')
  fs.writeFileSync(path.join(DOCS_DIR, 'projects.md'), lines.join('\n'), 'utf-8')
}

// ── main ──

function build() {
  const warnings = []
  const repos = collectRepos(warnings)
  const docPaths = discoverDocs(warnings)
  const docs = copyKnowledgeDocs(docPaths, warnings)

  const sidebar = buildSidebar(docs)
  const tags = buildTagIndex(docs)
  const calendar = buildCalendar(docs)

  const projectSet = new Set(docs.map((d) => d.project))
  const projects = [...projectSet]
    .filter((p) => p !== '_root')
    .map((p) => ({ project: p, docs_count: docs.filter((d) => d.project === p).length }))
    .sort((a, b) => b.docs_count - a.docs_count)

  fs.mkdirSync(VITEPRESS_DIR, { recursive: true })
  fs.writeFileSync(SIDEBAR_OUTPUT, JSON.stringify(sidebar, null, 2) + '\n', 'utf-8')

  const meta = {
    generated_at: new Date().toISOString(),
    stats: { docs_count: docs.length, projects_count: projects.length, repos_count: repos.length },
    tags,
    calendar,
    projects,
    repos,
    recent_docs: docs
      .sort((a, b) => {
        const tA = Date.parse(b.updated || b.created || '') || 0
        const tB = Date.parse(a.updated || a.created || '') || 0
        return tA - tB
      })
      .slice(0, 20)
      .map((d) => ({ title: d.title, path: d.path, project: d.project, updated: d.updated || d.created })),
  }
  fs.writeFileSync(META_OUTPUT, JSON.stringify(meta, null, 2) + '\n', 'utf-8')

  const publicDir = path.join(DOCS_DIR, 'public')
  fs.mkdirSync(publicDir, { recursive: true })
  fs.writeFileSync(path.join(publicDir, 'meta.generated.json'), JSON.stringify(meta, null, 2) + '\n', 'utf-8')

  writeTagsPage(tags)
  writeProjectsPage(projects, repos)

  console.log(`✓ sidebar → ${path.relative(APP_ROOT, SIDEBAR_OUTPUT)}`)
  console.log(`✓ meta    → ${path.relative(APP_ROOT, META_OUTPUT)}`)
  console.log(`✓ 文档 ${docs.length} 篇 → docs/knowledge/`)
  console.log(`✓ 项目 ${projects.length} 个，标签 ${Object.keys(tags).length} 种`)
  if (warnings.length) {
    console.log(`⚠ ${warnings.length} 条警告：`)
    for (const w of warnings.slice(0, 10)) console.log(`  - ${w}`)
    if (warnings.length > 10) console.log(`  ... 其余 ${warnings.length - 10} 条省略`)
  }
}

build()
