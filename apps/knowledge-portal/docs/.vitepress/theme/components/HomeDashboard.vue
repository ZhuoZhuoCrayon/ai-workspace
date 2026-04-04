<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { withBase } from 'vitepress'

interface Meta {
  stats: { docs_count: number; projects_count: number; repos_count: number }
  recent_docs: { title: string; path: string; project: string; updated: string }[]
  calendar: Record<string, number>
  tags: Record<string, { title: string; path: string; project: string }[]>
  projects: { project: string; docs_count: number }[]
}

const meta = ref<Meta | null>(null)

onMounted(async () => {
  try {
    const res = await fetch(withBase('meta.generated.json'))
    if (res.ok) meta.value = await res.json()
  } catch { /* graceful degradation */ }
})
</script>

<template>
  <div v-if="meta" class="dashboard">
    <div class="stat-cards">
      <div class="stat-card">
        <span class="stat-label">文档</span>
        <span class="stat-value">{{ meta.stats.docs_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">项目</span>
        <span class="stat-value">{{ meta.stats.projects_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">仓库</span>
        <span class="stat-value">{{ meta.stats.repos_count }}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">标签</span>
        <span class="stat-value">{{ Object.keys(meta.tags).length }}</span>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="recent-section">
        <h3>最近更新</h3>
        <ul class="recent-list">
          <li v-for="doc in meta.recent_docs" :key="doc.path">
            <a :href="withBase(doc.path)">{{ doc.title }}</a>
            <span class="recent-meta">{{ doc.project }} · {{ doc.updated?.slice(0, 10) || '—' }}</span>
          </li>
        </ul>
      </div>

      <div class="projects-section">
        <h3>项目分布</h3>
        <ul class="project-list">
          <li v-for="p in meta.projects" :key="p.project">
            <a :href="withBase(`knowledge/${p.project}/INDEX`)">{{ p.project }}</a>
            <span class="project-count">{{ p.docs_count }}</span>
          </li>
        </ul>
      </div>
    </div>

    <div class="calendar-section">
      <h3>活动日历</h3>
      <ActivityCalendar :data="meta.calendar" />
    </div>

    <div class="tags-section">
      <h3>热门标签</h3>
      <TagCloud :tags="meta.tags" :limit="30" />
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 960px;
  margin: 0 auto;
  padding: 1.5rem 0;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  padding: 1.2rem 1rem;
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  margin-bottom: 0.3rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--vp-c-brand-1);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

h3 {
  font-size: 1.1rem;
  margin: 0 0 0.8rem;
  color: var(--vp-c-text-1);
}

.recent-list,
.project-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.recent-list li {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.recent-list a {
  color: var(--vp-c-text-1);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.92rem;
}

.recent-list a:hover {
  color: var(--vp-c-brand-1);
}

.recent-meta {
  font-size: 0.78rem;
  color: var(--vp-c-text-3);
}

.project-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
}

.project-list a {
  color: var(--vp-c-text-1);
  text-decoration: none;
  font-weight: 500;
  font-size: 0.92rem;
}

.project-list a:hover {
  color: var(--vp-c-brand-1);
}

.project-count {
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-2);
  padding: 0.15rem 0.55rem;
  border-radius: 10px;
  font-size: 0.78rem;
  font-weight: 600;
}

.calendar-section,
.tags-section {
  margin-bottom: 2rem;
}

@media (max-width: 640px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
</style>
