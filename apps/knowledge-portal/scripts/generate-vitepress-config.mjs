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
    if (parts.length < 3 || parts[1].toLowerCase().endsWith('.md')) {
      return { visibility: 'public', project: '_root' }
    }
    return { visibility: 'public', project: parts[1] ?? '_unknown' }
  }
  if (parts.length < 4 || parts[2].toLowerCase().endsWith('.md')) {
    return { visibility: 'private', project: '_root' }
  }
  return { visibility: 'private', project: parts[2] ?? '_unknown' }
}

function parseIssueKey(relPath) {
  const m1 = relPath.match(/^knowledge\/([^/]+)\/issues\/([^/]+)\//)
  if (m1) return `public:${m1[1]}:${m1[2]}`
  const m2 = relPath.match(/^private\/knowledge\/([^/]+)\/issues\/([^/]+)\//)
  if (m2) return `private:${m2[1]}:${m2[2]}`
  return ''
}

function extractLinks(markdown) {
  const links = []
  const re = /\[[^\]]+\]\(([^)]+)\)/g
  let m = re.exec(markdown)
  while (m) {
    links.push(m[1])
    m = re.exec(markdown)
  }
  return links
}

function pickTitle(data, content, fallback) {
  if (typeof data.title === 'string' && data.title.trim()) return data.title.trim()
  const heading = content.match(/^#\s+(.+)$/m)
  return heading?.[1]?.trim() || fallback
}

function normalizeDate(value) {
  if (!value) return ''
  if (value instanceof Date) return value.toISOString().slice(0, 10)
  const text = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text
  const ts = Date.parse(text)
  return Number.isNaN(ts) ? '' : new Date(ts).toISOString().slice(0, 10)
}

function normalizeOutputRelMd(sourceRelPath) {
  const prefix = sourceRelPath.startsWith('knowledge/') ? 'knowledge/' : 'private/knowledge/'
  const rest = sourceRelPath.slice(prefix.length)
  const dir = path.posix.dirname(rest)
  const base = path.posix.basename(rest).toLowerCase()

  const outputBase = base === 'readme.md' || base === 'index.md' ? 'index.md' : base
  const outputRel = prefix === 'knowledge/' ? `knowledge/${dir === '.' ? '' : `${dir}/`}${outputBase}` : `knowledge/private/knowledge/${dir === '.' ? '' : `${dir}/`}${outputBase}`
  return outputRel.replace(/\/\//g, '/')
}

function toRoute(relMdPath) {
  const clean = relMdPath.replace(/\.md$/i, '')
  if (clean.endsWith('/index')) {
    const root = clean.slice(0, -'/index'.length)
    return `${root ? `/${root}` : ''}/`
  }
  return `/${clean}`
}

function rewriteMarkdownLinks(content) {
  return content.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, text, rawTarget) => {
    const target = String(rawTarget).trim()
    if (
      !target
      || target.startsWith('#')
      || /^https?:\/\//i.test(target)
      || target.startsWith('mailto:')
      || target.startsWith('tel:')
    ) {
      return match
    }

    const [pathPart, anchor = ''] = target.split('#', 2)
    if (!/\.(md|html)$/i.test(pathPart)) return match

    const dirname = path.posix.dirname(pathPart)
    const base = path.posix.basename(pathPart, path.posix.extname(pathPart)).toLowerCase()

    let rewritten = ''
    if (base === 'index' || base === 'readme') {
      rewritten = dirname === '.' ? './' : `${dirname}/`
    } else {
      rewritten = dirname === '.' ? `./${base}` : `${dirname}/${base}`
    }

    const withAnchor = anchor ? `${rewritten}#${anchor}` : rewritten
    return `[${text}](${withAnchor})`
  })
}

function safeParseFrontmatter(raw) {
  try {
    const parsed = matter(raw)
    return { data: parsed.data, content: parsed.content, fallback: false }
  } catch {
    const lines = raw.split('\n')
    if (lines[0]?.trim() !== '---') {
      return { data: {}, content: raw, fallback: true }
    }

    const data = {}
    let endIdx = -1
    for (let i = 1; i < lines.length; i += 1) {
      const line = lines[i]
      if (line.trim() === '---') {
        endIdx = i
        break
      }
      if (line.trim() === '' || /^##?\s/.test(line)) {
        endIdx = i
        break
      }

      const colonIdx = line.indexOf(':')
      if (colonIdx > 0) {
        const key = line.slice(0, colonIdx).trim()
        const value = line.slice(colonIdx + 1).trim()
        data[key] = value
      }
    }

    const content = endIdx >= 0
      ? lines.slice(endIdx + (lines[endIdx]?.trim() === '---' ? 1 : 0)).join('\n')
      : lines.slice(1).join('\n')
    return { data, content, fallback: true }
  }
}

function buildCleanMarkdown(data, content) {
  const fields = [
    'title',
    'description',
    'tags',
    'created',
    'updated',
    'issue_readme_route',
    'issue_plan_route',
  ]

  const normalized = {}
  for (const key of fields) {
    const value = data[key]
    if (value === undefined || value === null || value === '') continue
    normalized[key] = Array.isArray(value) ? value.map((item) => String(item)) : String(value)
  }

  if (Object.keys(normalized).length === 0) return content

  const yamlLines = Object.entries(normalized).map(([key, value]) => {
    if (Array.isArray(value)) {
      return `${key}: [${value.map((item) => JSON.stringify(item)).join(', ')}]`
    }
    return `${key}: ${JSON.stringify(value)}`
  })

  return `---\n${yamlLines.join('\n')}\n---\n${content}`
}

function collectRepos(warnings) {
  const repos = []
  for (const src of REPO_SOURCES) {
    const absPath = path.join(WORKSPACE_ROOT, src.file)
    if (!fs.existsSync(absPath)) continue

    try {
      const rows = parseRegistryFile(absPath, src.format)
      for (const row of rows) {
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
    } catch (error) {
      warnings.push(`仓库注册表解析失败：${src.file}（${String(error)}）`)
    }
  }

  const uniq = new Map()
  for (const repo of repos) {
    const key = `${repo.visibility}:${repo.name}`
    if (repo.name && !uniq.has(key)) uniq.set(key, repo)
  }
  return [...uniq.values()].sort((a, b) => a.name.localeCompare(b.name))
}

function discoverDocs(warnings) {
  const queue = INDEX_ROOTS.map((item) => path.join(WORKSPACE_ROOT, item)).filter((item) => fs.existsSync(item))
  const visited = new Set()
  const allPaths = new Set()

  while (queue.length > 0) {
    const current = queue.shift()
    if (!current || visited.has(current)) continue
    visited.add(current)

    const content = safeRead(current)
    if (!content) {
      warnings.push(`无法读取索引：${normalizeRelPath(current)}`)
      continue
    }
    allPaths.add(current)

    for (const rawLink of extractLinks(content)) {
      const clean = rawLink.split('#')[0]?.trim()
      if (!clean || !/\.md$/i.test(clean) || /^https?:\/\//i.test(clean) || clean.startsWith('mailto:')) {
        continue
      }

      const target = path.resolve(path.dirname(current), decodeURIComponent(clean))
      if (!target.startsWith(WORKSPACE_ROOT)) continue
      if (!fs.existsSync(target)) {
        warnings.push(`链接文件不存在：${normalizeRelPath(target)}`)
        continue
      }

      allPaths.add(target)
      const base = path.basename(target).toLowerCase()
      if (base === 'index.md' || base === 'readme.md') queue.push(target)
    }
  }

  const expanded = new Set(allPaths)
  for (const absPath of allPaths) {
    const relPath = normalizeRelPath(absPath)
    if (!parseIssueKey(relPath)) continue

    const dir = path.dirname(absPath)
    let children = []
    try {
      children = fs.readdirSync(dir)
    } catch {
      continue
    }

    for (const child of children) {
      if (!/^readme\.md$/i.test(child) && !/^plan\.md$/i.test(child)) continue
      const childPath = path.join(dir, child)
      if (fs.existsSync(childPath)) expanded.add(childPath)
    }
  }

  return [...expanded].filter((item) => isKnowledgePath(normalizeRelPath(item))).sort()
}

function copyKnowledgeDocs(docAbsPaths, warnings) {
  fs.rmSync(KNOWLEDGE_DEST, { recursive: true, force: true })

  const entries = []
  for (const absPath of docAbsPaths) {
    const sourceRel = normalizeRelPath(absPath)
    const raw = safeRead(absPath)
    if (!raw) continue

    const parsed = safeParseFrontmatter(raw)
    if (parsed.fallback) {
      warnings.push(`frontmatter 解析异常，已降级：${sourceRel}`)
    }

    const outputRelMd = normalizeOutputRelMd(sourceRel)
    const route = toRoute(outputRelMd)
    const baseLower = path.posix.basename(sourceRel).toLowerCase()
    const sourceKind = baseLower === 'readme.md' ? 'readme' : baseLower === 'plan.md' ? 'plan' : baseLower === 'index.md' ? 'index' : baseLower.replace(/\.md$/i, '')

    const parsedProject = parseProject(sourceRel)
    const created = normalizeDate(parsed.data.created)
    const updated = normalizeDate(parsed.data.updated)
    const issueKey = parseIssueKey(sourceRel)

    entries.push({
      sourceRel,
      outputRelMd,
      route,
      sourceKind,
      issueKey,
      data: parsed.data,
      content: rewriteMarkdownLinks(parsed.content),
      title: pickTitle(parsed.data, parsed.content, path.posix.basename(sourceRel, '.md')),
      description: typeof parsed.data.description === 'string' ? parsed.data.description : '',
      tags: Array.isArray(parsed.data.tags) ? parsed.data.tags.map((item) => String(item)) : [],
      created,
      updated,
      project: parsedProject.project,
      visibility: parsedProject.visibility,
    })
  }

  const issueMap = new Map()
  for (const entry of entries) {
    if (!entry.issueKey) continue
    const current = issueMap.get(entry.issueKey) ?? { readme: '', plan: '' }
    if (entry.sourceKind === 'readme') current.readme = entry.route
    if (entry.sourceKind === 'plan') current.plan = entry.route
    issueMap.set(entry.issueKey, current)
  }

  const docs = []
  for (const entry of entries) {
    const issueRoutes = entry.issueKey ? issueMap.get(entry.issueKey) : null
    const mergedData = {
      ...entry.data,
      created: entry.created,
      updated: entry.updated,
      issue_readme_route: issueRoutes?.readme || '',
      issue_plan_route: issueRoutes?.plan || '',
    }

    const cleanMd = buildCleanMarkdown(mergedData, entry.content)
    const destPath = path.join(DOCS_DIR, entry.outputRelMd)
    fs.mkdirSync(path.dirname(destPath), { recursive: true })
    fs.writeFileSync(destPath, cleanMd, 'utf-8')

    docs.push({
      route: entry.route,
      path: entry.outputRelMd,
      title: entry.title,
      description: entry.description,
      tags: entry.tags,
      created: entry.created,
      updated: entry.updated,
      project: entry.project,
      visibility: entry.visibility,
      source_kind: entry.sourceKind,
      issue_key: entry.issueKey,
    })
  }

  return docs
}

function buildSidebar(docs) {
  const byProject = new Map()
  for (const doc of docs) {
    if (!byProject.has(doc.project)) byProject.set(doc.project, [])
    byProject.get(doc.project).push(doc)
  }

  const sidebar = {}
  for (const [project, projectDocs] of [...byProject.entries()].filter(([name]) => name !== '_root').sort((a, b) => a[0].localeCompare(b[0]))) {
    const prefix = `/knowledge/${project}/`

    const groups = []

    const rootItems = projectDocs
      .filter((doc) => doc.path === `knowledge/${project}/index.md`)
      .map((doc) => ({ text: doc.title, link: doc.route }))
    if (rootItems.length > 0) {
      groups.push({ text: project, items: rootItems })
    }

    const issueDocs = projectDocs.filter((doc) => doc.path.startsWith(`knowledge/${project}/issues/`) && doc.issue_key)
    if (issueDocs.length > 0) {
      const byIssue = new Map()
      for (const doc of issueDocs) {
        const key = doc.issue_key
        if (!byIssue.has(key)) byIssue.set(key, [])
        byIssue.get(key).push(doc)
      }

      const items = [...byIssue.values()]
        .map((candidates) => {
          const primary = candidates.find((doc) => doc.source_kind === 'readme') || candidates[0]
          return {
            text: primary.title,
            link: primary.route,
            updated: primary.updated || primary.created,
          }
        })
        .sort((a, b) => (Date.parse(b.updated || '') || 0) - (Date.parse(a.updated || '') || 0))
        .map(({ text, link }) => ({ text, link }))

      const issueIndex = projectDocs.find((doc) => doc.path === `knowledge/${project}/issues/index.md`)
      if (issueIndex) {
        items.push({ text: issueIndex.title, link: issueIndex.route })
      }

      groups.push({ text: 'issues', collapsed: false, items })
    }

    const byKind = new Map()
    for (const doc of projectDocs.filter((item) => !item.path.startsWith(`knowledge/${project}/issues/`) && item.path !== `knowledge/${project}/index.md`)) {
      const rel = doc.path.replace(`knowledge/${project}/`, '')
      const kind = rel.includes('/') ? rel.split('/')[0] : '_root'
      if (!byKind.has(kind)) byKind.set(kind, [])
      byKind.get(kind).push(doc)
    }

    for (const [kind, kindDocs] of [...byKind.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const items = kindDocs
        .sort((a, b) => (Date.parse(b.updated || b.created || '') || 0) - (Date.parse(a.updated || a.created || '') || 0))
        .map((doc) => ({ text: doc.title, link: doc.route }))
      if (items.length > 0) {
        groups.push({ text: kind, collapsed: true, items })
      }
    }

    sidebar[prefix] = groups
  }

  return sidebar
}

function buildTagIndex(docs) {
  const grouped = new Map()
  for (const doc of docs) {
    for (const tag of doc.tags) {
      if (!grouped.has(tag)) grouped.set(tag, [])
      grouped.get(tag).push({ title: doc.title, route: doc.route, project: doc.project })
    }
  }
  return Object.fromEntries([...grouped.entries()].sort((a, b) => b[1].length - a[1].length))
}

function buildCalendar(docs) {
  const grouped = new Map()
  for (const doc of docs) {
    const date = doc.updated || doc.created
    if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) continue
    grouped.set(date, (grouped.get(date) ?? 0) + 1)
  }
  return Object.fromEntries([...grouped.entries()].sort())
}

function writeTagsPage(tags) {
  const lines = ['---', 'title: 标签索引', 'sidebar: false', '---', '', '# 标签索引', '']
  for (const [tag, tagDocs] of Object.entries(tags)) {
    lines.push(`## ${tag}`, '')
    for (const doc of tagDocs) {
      lines.push(`- [${doc.title}](${doc.route}) <small>${doc.project}</small>`)
    }
    lines.push('')
  }
  fs.writeFileSync(path.join(DOCS_DIR, 'tags.md'), lines.join('\n'), 'utf-8')
}

function writeProjectsPage(projects) {
  const lines = [
    '---',
    'title: 项目概览',
    'sidebar: false',
    '---',
    '',
    '# 项目概览',
    '',
    '| 项目 | 文档数 | 描述 |',
    '|------|--------|------|',
  ]

  for (const project of projects) {
    lines.push(`| [${project.project}](${project.route}) | ${project.docs_count} | ${project.description || ''} |`)
  }
  lines.push('')
  fs.writeFileSync(path.join(DOCS_DIR, 'projects.md'), lines.join('\n'), 'utf-8')
}

function build() {
  const warnings = []
  const repos = collectRepos(warnings)
  const docAbsPaths = discoverDocs(warnings)
  const docs = copyKnowledgeDocs(docAbsPaths, warnings)

  const docsForNav = docs.filter((doc) => !(doc.issue_key && doc.source_kind === 'plan'))
  const sidebar = buildSidebar(docsForNav)
  const tags = buildTagIndex(docsForNav)
  const calendar = buildCalendar(docsForNav)

  const projectMap = new Map()
  for (const doc of docsForNav) {
    const key = doc.project
    const current = projectMap.get(key) ?? {
      project: doc.project,
      docs_count: 0,
      route: `/knowledge/${doc.project}/`,
      description: '',
    }

    current.docs_count += 1
    if (doc.path === `knowledge/${doc.project}/index.md`) {
      current.route = doc.route
    }

    const repo = repos.find((item) => item.name === doc.project)
    if (repo && !current.description) current.description = repo.description

    projectMap.set(key, current)
  }

  const projects = [...projectMap.values()]
    .filter((item) => item.project !== '_root')
    .sort((a, b) => b.docs_count - a.docs_count || a.project.localeCompare(b.project))

  const recentDocs = [...docsForNav]
    .sort((a, b) => (Date.parse(b.updated || b.created || '') || 0) - (Date.parse(a.updated || a.created || '') || 0))
    .slice(0, 20)
    .map((doc) => ({
      title: doc.title,
      route: doc.route,
      project: doc.project,
      updated: doc.updated || doc.created,
    }))

  const meta = {
    generated_at: new Date().toISOString(),
    stats: {
      docs_count: docsForNav.length,
      projects_count: projects.length,
      repos_count: repos.length,
    },
    tags,
    calendar,
    projects,
    repos,
    recent_docs: recentDocs,
  }

  fs.mkdirSync(VITEPRESS_DIR, { recursive: true })
  fs.writeFileSync(SIDEBAR_OUTPUT, `${JSON.stringify(sidebar, null, 2)}\n`, 'utf-8')
  fs.writeFileSync(META_OUTPUT, `${JSON.stringify(meta, null, 2)}\n`, 'utf-8')

  const publicDir = path.join(DOCS_DIR, 'public')
  fs.mkdirSync(publicDir, { recursive: true })
  fs.writeFileSync(path.join(publicDir, 'meta.generated.json'), `${JSON.stringify(meta, null, 2)}\n`, 'utf-8')

  writeTagsPage(tags)
  writeProjectsPage(projects)

  console.log(`✓ sidebar → ${path.relative(APP_ROOT, SIDEBAR_OUTPUT)}`)
  console.log(`✓ meta    → ${path.relative(APP_ROOT, META_OUTPUT)}`)
  console.log(`✓ 文档 ${docsForNav.length} 篇 → docs/knowledge/`)
  console.log(`✓ 项目 ${projects.length} 个，标签 ${Object.keys(tags).length} 种`)
  if (warnings.length > 0) {
    console.log(`⚠ ${warnings.length} 条警告：`)
    for (const warning of warnings.slice(0, 10)) {
      console.log(`  - ${warning}`)
    }
    if (warnings.length > 10) {
      console.log(`  ... 其余 ${warnings.length - 10} 条省略`)
    }
  }
}

build()
