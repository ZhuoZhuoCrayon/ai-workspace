import fs from 'node:fs'
import path from 'node:path'

import matter from 'gray-matter'
import yaml from 'js-yaml'

const APP_ROOT = path.resolve(import.meta.dirname, '..')
const WORKSPACE_ROOT = path.resolve(APP_ROOT, '..', '..')
const OUTPUT_FILE = path.join(APP_ROOT, 'public', 'data', 'knowledge.json')

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
  if (!Array.isArray(parsed)) return []
  return parsed
}

function collectRepos(warnings) {
  const repos = []

  for (const source of REPO_SOURCES) {
    const absPath = path.join(WORKSPACE_ROOT, source.file)
    if (!fs.existsSync(absPath)) continue

    try {
      const rows = parseRegistryFile(absPath, source.format)
      for (const row of rows) {
        if (!row || typeof row !== 'object') continue
        repos.push({
          name: String(row.name ?? ''),
          description: String(row.description ?? ''),
          git_url: String(row.git_url ?? ''),
          branch: String(row.branch ?? ''),
          local_path: String(row.local_path ?? ''),
          language: String(row.language ?? ''),
          visibility: source.visibility,
          source_file: source.file,
        })
      }
    } catch (error) {
      warnings.push(`仓库注册表解析失败：${source.file}（${String(error)}）`)
    }
  }

  const unique = new Map()
  for (const repo of repos) {
    const key = `${repo.visibility}:${repo.name}`
    if (!repo.name || unique.has(key)) continue
    unique.set(key, repo)
  }
  return [...unique.values()].sort((a, b) => a.name.localeCompare(b.name))
}

function extractLinks(markdown) {
  const links = []
  const pattern = /\[[^\]]+\]\(([^)]+)\)/g
  let match = pattern.exec(markdown)
  while (match) {
    links.push(match[1])
    match = pattern.exec(markdown)
  }
  return links
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
    return { visibility: 'public', project: parts[1] ?? '_unknown' }
  }
  return { visibility: 'private', project: parts[2] ?? '_unknown' }
}

function pickTitle(frontmatter, content, fallback) {
  if (typeof frontmatter.title === 'string' && frontmatter.title.trim()) {
    return frontmatter.title.trim()
  }
  const heading = content.match(/^#\s+(.+)$/m)
  return heading?.[1]?.trim() || fallback
}

function toPlainText(markdown) {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[[^\]]+\]\(([^)]+)\)/g, ' ')
    .replace(/[>#*_~\-\|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function collectDocs(warnings) {
  const queue = INDEX_ROOTS.map((p) => path.join(WORKSPACE_ROOT, p)).filter((p) => fs.existsSync(p))
  const visitedIndexes = new Set()
  const docs = new Set()

  while (queue.length > 0) {
    const current = queue.shift()
    if (!current || visitedIndexes.has(current)) continue
    visitedIndexes.add(current)

    const content = safeRead(current)
    if (!content) {
      warnings.push(`无法读取索引：${normalizeRelPath(current)}`)
      continue
    }

    docs.add(current)

    for (const rawLink of extractLinks(content)) {
      const withoutAnchor = rawLink.split('#')[0]?.trim()
      if (!withoutAnchor || /^https?:\/\//i.test(withoutAnchor) || withoutAnchor.startsWith('mailto:')) {
        continue
      }
      if (!withoutAnchor.endsWith('.md')) continue

      const decoded = decodeURIComponent(withoutAnchor)
      const target = path.resolve(path.dirname(current), decoded)
      if (!target.startsWith(WORKSPACE_ROOT)) {
        warnings.push(`越界链接已忽略：${rawLink}（来源 ${normalizeRelPath(current)}）`)
        continue
      }
      if (!fs.existsSync(target)) {
        warnings.push(`链接文件不存在：${normalizeRelPath(target)}（来源 ${normalizeRelPath(current)}）`)
        continue
      }

      docs.add(target)
      if (path.basename(target).toLowerCase() === 'index.md') {
        queue.push(target)
      }
    }
  }

  const parsed = []
  for (const absPath of [...docs].sort()) {
    const relPath = normalizeRelPath(absPath)
    if (!isKnowledgePath(relPath)) continue

    const raw = safeRead(absPath)
    if (!raw) continue

    let data = {}
    let content = raw
    try {
      const parsed = matter(raw)
      data = parsed.data
      content = parsed.content
    } catch (error) {
      warnings.push(`frontmatter 解析失败，已按纯 Markdown 处理：${relPath}（${String(error)}）`)
    }
    const { visibility, project } = parseProject(relPath)
    const basename = path.basename(relPath)
    const plainText = toPlainText(content)
    const title = pickTitle(data, content, relPath)

    parsed.push({
      id: Buffer.from(relPath).toString('base64url'),
      path: relPath,
      title,
      description: typeof data.description === 'string' ? data.description : '',
      tags: Array.isArray(data.tags) ? data.tags.map((item) => String(item)) : [],
      created: typeof data.created === 'string' ? data.created : '',
      updated: typeof data.updated === 'string' ? data.updated : '',
      project,
      visibility,
      kind: basename.replace(/\.md$/i, '').toLowerCase(),
      excerpt: plainText.slice(0, 180),
      plain_text: plainText,
      content,
    })
  }

  parsed.sort((a, b) => {
    const timeA = Date.parse(a.updated || a.created || '') || 0
    const timeB = Date.parse(b.updated || b.created || '') || 0
    if (timeA !== timeB) return timeB - timeA
    return a.path.localeCompare(b.path)
  })

  return parsed
}

function build() {
  const warnings = []
  const repos = collectRepos(warnings)
  const docs = collectDocs(warnings)

  const projectsInDocs = new Set(docs.map((doc) => `${doc.visibility}:${doc.project}`))
  const projectStats = [...projectsInDocs]
    .map((key) => {
      const [visibility, project] = key.split(':')
      const docsCount = docs.filter((item) => item.project === project && item.visibility === visibility).length
      const repo = repos.find((item) => item.name === project && item.visibility === visibility)
      return {
        project,
        visibility,
        docs_count: docsCount,
        repo_name: repo?.name || project,
        repo_description: repo?.description || '',
      }
    })
    .sort((a, b) => b.docs_count - a.docs_count || a.project.localeCompare(b.project))

  const payload = {
    generated_at: new Date().toISOString(),
    repos,
    projects: projectStats,
    docs,
    stats: {
      docs_count: docs.length,
      projects_count: projectStats.length,
      repos_count: repos.length,
      warning_count: warnings.length,
    },
    warnings,
  }

  fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true })
  fs.writeFileSync(OUTPUT_FILE, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8')

  console.log(`知识数据已生成：${normalizeRelPath(OUTPUT_FILE)}`)
  console.log(`文档 ${payload.stats.docs_count} 篇，项目 ${payload.stats.projects_count} 个，警告 ${payload.stats.warning_count} 条。`)
  if (warnings.length > 0) {
    console.log('--- warnings ---')
    for (const warning of warnings.slice(0, 20)) {
      console.log(`- ${warning}`)
    }
    if (warnings.length > 20) {
      console.log(`... 其余 ${warnings.length - 20} 条省略`)
    }
  }
}

build()
