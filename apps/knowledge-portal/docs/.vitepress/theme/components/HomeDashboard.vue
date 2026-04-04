<script setup lang="ts">
import { computed, ref } from 'vue'
import { withBase } from 'vitepress'
import metaData from '../../meta.generated.json'

type DocType = 'all' | 'issue' | 'snippet' | 'troubleshooting' | 'other'

interface Meta {
  stats: { docs_count: number; projects_count: number; repos_count: number }
  recent_docs: { title: string; route: string; project: string; updated: string }[]
  calendar: Record<string, number>
  tags: Record<string, { title: string; route: string; project: string }[]>
  projects: { project: string; docs_count: number; route: string; repo_url?: string; repo_platform?: string }[]
}

const meta = metaData as Meta
const activeType = ref<DocType>('all')

const typeLabels: Record<DocType, string> = {
  all: '全部',
  issue: '需求',
  snippet: '片段',
  troubleshooting: '排障',
  other: '其他',
}

const typedRecentDocs = computed(() => {
  const detectType = (route: string): DocType => {
    if (route.includes('/issues/')) return 'issue'
    if (route.includes('/snippets/')) return 'snippet'
    if (route.includes('/troubleshooting/')) return 'troubleshooting'
    return 'other'
  }

  return meta.recent_docs.map((doc) => ({ ...doc, type: detectType(doc.route) }))
})

const typeOptions = computed(() => {
  const counts = typedRecentDocs.value.reduce<Record<DocType, number>>(
    (acc, doc) => {
      acc[doc.type] += 1
      return acc
    },
    { all: typedRecentDocs.value.length, issue: 0, snippet: 0, troubleshooting: 0, other: 0 },
  )

  return (Object.keys(typeLabels) as DocType[])
    .filter((type) => counts[type] > 0)
    .map((type) => ({ key: type, label: typeLabels[type], count: counts[type] }))
})

const filteredRecentDocs = computed(() => {
  if (activeType.value === 'all') return typedRecentDocs.value
  return typedRecentDocs.value.filter((doc) => doc.type === activeType.value)
})

const yearUpdatedDocs = computed(() => {
  return Object.values(meta.calendar).reduce((sum, count) => sum + count, 0)
})

const tagCount = computed(() => {
  return Object.keys(meta.tags).length
})
</script>

<template>
  <div class="dashboard">
    <section class="panel calendar-section">
      <div class="panel-head">
        <div>
          <h3>活动日志</h3>
          <p class="activity-summary">
            过去一年共更新
            <a :href="withBase('/knowledge/')" class="summary-link">{{ yearUpdatedDocs }}</a>
            篇文档，当前共有文档
            <a :href="withBase('/knowledge/')" class="summary-link">{{ meta.stats.docs_count }}</a>
            篇，项目
            <a :href="withBase('/projects')" class="summary-link">{{ meta.stats.projects_count }}</a>
            个，仓库
            <a :href="withBase('/projects')" class="summary-link">{{ meta.stats.repos_count }}</a>
            个，标签
            <a :href="withBase('/tags')" class="summary-link">{{ tagCount }}</a>
            个。
          </p>
        </div>
        <a :href="withBase('/knowledge/')" class="ghost-link">查看全部文档</a>
      </div>
      <ActivityCalendar :data="meta.calendar" />
    </section>

    <div class="dashboard-grid">
      <section class="panel recent-section">
        <div class="panel-head">
          <h3>最近更新</h3>
          <span class="section-meta">{{ filteredRecentDocs.length }} 篇</span>
        </div>

        <div class="recent-filters">
          <button
            v-for="item in typeOptions"
            :key="item.key"
            type="button"
            class="filter-chip"
            :class="{ 'is-active': activeType === item.key }"
            :aria-pressed="activeType === item.key"
            @click="activeType = item.key"
          >
            {{ item.label }}
            <span class="filter-count">{{ item.count }}</span>
          </button>
        </div>

        <div class="recent-list-wrap">
          <ul class="recent-list">
            <li v-for="doc in filteredRecentDocs" :key="doc.route">
              <a :href="withBase(doc.route)" :title="doc.title">{{ doc.title }}</a>
              <span class="recent-meta">{{ doc.project }} · {{ doc.updated?.slice(0, 10) || '—' }}</span>
            </li>
          </ul>
        </div>
      </section>

      <section class="panel projects-section">
        <div class="panel-head">
          <h3>项目分布</h3>
          <a :href="withBase('/projects')" class="section-link">查看全部</a>
        </div>
        <div class="projects-toolbar">
          <span class="projects-summary">覆盖 {{ meta.projects.length }} 个项目</span>
        </div>
        <ul class="project-list">
          <li v-for="p in meta.projects" :key="p.project">
            <a :href="withBase(p.route)">{{ p.project }}</a>
            <div class="project-actions">
              <a
                v-if="p.repo_url"
                class="repo-link"
                :href="p.repo_url"
                target="_blank"
                rel="noopener noreferrer"
                :title="`打开 ${p.project} 仓库`"
              >
                {{ p.repo_platform || 'Git' }}
              </a>
              <span class="project-count">{{ p.docs_count }}</span>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <section class="panel tags-section">
      <div class="panel-head">
        <h3>热门标签</h3>
        <a :href="withBase('/tags')" class="section-link">标签索引</a>
      </div>
      <TagCloud :tags="meta.tags" :limit="30" />
    </section>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: var(--kp-content-max);
  margin: 0 auto;
  padding: 0;
}

.panel {
  background:
    radial-gradient(circle at right top, color-mix(in srgb, var(--vp-c-brand-1) 8%, transparent) 0%, transparent 44%),
    linear-gradient(180deg, color-mix(in srgb, var(--vp-c-bg-soft) 76%, transparent) 0%, var(--vp-c-bg) 100%);
  border: 1px solid var(--vp-c-divider);
  border-radius: 18px;
  padding: 1rem 1.05rem 1.1rem;
  box-shadow: 0 14px 30px rgba(2, 8, 23, 0.05);
  transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.22s ease;
}

.panel:hover {
  border-color: color-mix(in srgb, var(--vp-c-brand-1) 24%, var(--vp-c-divider));
  box-shadow: 0 18px 36px rgba(2, 8, 23, 0.08);
  transform: translateY(-1px);
}

.dashboard > .panel + .panel,
.dashboard-grid,
.tags-section {
  margin-top: 1rem;
}

.dashboard-grid > .panel {
  margin-top: 0;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.8rem;
  padding-bottom: 0.55rem;
  border-bottom: 1px solid color-mix(in srgb, var(--vp-c-divider) 78%, transparent);
}

.recent-section .panel-head,
.projects-section .panel-head {
  height: 37px;
  box-sizing: border-box;
}

h3 {
  font-size: 1.03rem;
  line-height: 1.3;
  margin: 0;
  letter-spacing: 0.01em;
  color: var(--vp-c-text-1);
}

.activity-summary {
  margin: 0.3rem 0 0;
  color: var(--vp-c-text-2);
  font-size: 0.885rem;
  line-height: 1.55;
}

.summary-link,
.section-link,
.ghost-link {
  color: var(--vp-c-brand-1);
  text-decoration: none;
  font-weight: 600;
}

.summary-link:hover,
.section-link:hover,
.ghost-link:hover {
  text-decoration: underline;
}

.ghost-link {
  flex-shrink: 0;
  font-size: 0.84rem;
  margin-top: 0.2rem;
}

.section-meta {
  font-size: 0.8rem;
  color: var(--vp-c-text-3);
  white-space: nowrap;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--vp-c-bg-soft) 84%, transparent);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr);
  gap: 1rem;
}

.recent-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-bottom: 0.72rem;
  min-height: 32px;
}

.projects-toolbar {
  display: flex;
  align-items: center;
  min-height: 32px;
  margin-bottom: 0.72rem;
}

.projects-summary {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.54rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--vp-c-divider) 78%, transparent);
  background: color-mix(in srgb, var(--vp-c-bg-soft) 90%, transparent);
  font-size: 0.76rem;
  color: var(--vp-c-text-3);
}

.filter-chip {
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-2);
  border-radius: 999px;
  padding: 0.22rem 0.58rem;
  font-size: 0.78rem;
  line-height: 1.35;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  cursor: pointer;
  transition: all 0.16s ease;
}

.filter-chip:hover {
  border-color: color-mix(in srgb, var(--vp-c-brand-1) 36%, var(--vp-c-divider));
  color: var(--vp-c-brand-1);
  transform: translateY(-1px);
}

.filter-chip.is-active {
  background: var(--vp-c-brand-soft);
  border-color: color-mix(in srgb, var(--vp-c-brand-1) 40%, var(--vp-c-divider));
  color: var(--vp-c-brand-1);
}

.filter-chip:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--vp-c-brand-1) 66%, transparent);
  outline-offset: 1px;
}

.filter-count {
  color: inherit;
  font-size: 0.72rem;
  opacity: 0.8;
}

.recent-list,
.project-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-list-wrap {
  max-height: 440px;
  overflow-y: auto;
  padding-right: 0.28rem;
  scrollbar-gutter: stable;
}

.recent-list li {
  padding: 0.5rem 0.06rem;
  border-bottom: 1px solid var(--vp-c-divider);
  display: flex;
  flex-direction: column;
  gap: 0.16rem;
  transition: background-color 0.16s ease;
}

.recent-list li:hover {
  background: color-mix(in srgb, var(--vp-c-brand-soft) 36%, transparent);
}

.recent-list li:last-child,
.project-list li:last-child {
  border-bottom: 0;
}

.recent-list a,
.project-list a {
  color: var(--vp-c-text-1);
  text-decoration: none;
  font-weight: 500;
}

.recent-list a {
  font-size: 0.915rem;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-list a {
  font-size: 0.9rem;
}

.recent-list a:hover,
.project-list a:hover {
  color: var(--vp-c-brand-1);
}

.recent-meta {
  font-size: 0.765rem;
  color: var(--vp-c-text-3);
}

.project-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.49rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
}

.project-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.repo-link {
  display: inline-flex;
  align-items: center;
  padding: 0.12rem 0.42rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--vp-c-brand-1) 28%, var(--vp-c-divider));
  background: color-mix(in srgb, var(--vp-c-brand-soft) 56%, transparent);
  color: var(--vp-c-brand-1);
  font-size: 0.69rem;
  font-weight: 600;
  text-decoration: none;
}

.repo-link:hover {
  background: color-mix(in srgb, var(--vp-c-brand-soft) 74%, transparent);
}

.project-count {
  background: color-mix(in srgb, var(--vp-c-bg-soft) 88%, transparent);
  color: var(--vp-c-text-2);
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.76rem;
  font-weight: 600;
  border: 1px solid color-mix(in srgb, var(--vp-c-divider) 72%, transparent);
}

.recent-list-wrap::-webkit-scrollbar {
  width: 7px;
}

.recent-list-wrap::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--vp-c-brand-1) 26%, var(--vp-c-bg-soft));
  border-radius: 999px;
}

.recent-list-wrap::-webkit-scrollbar-track {
  background: transparent;
}

:global(.dark) .panel {
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.3);
}

:global(.dark) .panel:hover {
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.42);
}

@media (max-width: 960px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .panel {
    border-radius: 14px;
    padding: 0.9rem 0.82rem;
  }

  .panel-head {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.35rem;
    padding-bottom: 0.45rem;
  }

  .recent-list-wrap {
    max-height: 360px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel,
  .filter-chip,
  .recent-list li,
  .recent-list a,
  .project-list a {
    transition: none !important;
    transform: none !important;
  }
}
</style>
