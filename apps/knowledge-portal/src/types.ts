export type Visibility = 'public' | 'private'

export interface RepoItem {
  name: string
  description: string
  git_url: string
  branch: string
  local_path: string
  language: string
  visibility: Visibility
  source_file: string
}

export interface ProjectItem {
  project: string
  visibility: Visibility
  docs_count: number
  repo_name: string
  repo_description: string
}

export interface KnowledgeDoc {
  id: string
  path: string
  title: string
  description: string
  tags: string[]
  created: string
  updated: string
  project: string
  visibility: Visibility
  kind: string
  excerpt: string
  plain_text: string
  content: string
}

export interface KnowledgeStats {
  docs_count: number
  projects_count: number
  repos_count: number
  warning_count: number
}

export interface KnowledgePayload {
  generated_at: string
  repos: RepoItem[]
  projects: ProjectItem[]
  docs: KnowledgeDoc[]
  stats: KnowledgeStats
  warnings: string[]
}
