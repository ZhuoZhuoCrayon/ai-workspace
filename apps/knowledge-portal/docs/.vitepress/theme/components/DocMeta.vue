<script setup lang="ts">
import { withBase } from 'vitepress'

defineProps<{
  tags?: string[]
  project?: string
  created?: string
  updated?: string
}>()
</script>

<template>
  <div class="doc-meta-bar">
    <span v-if="project" class="meta-item">
      <a :href="withBase(`/knowledge/${project}/`)">{{ project }}</a>
    </span>
    <span v-if="updated || created" class="meta-item date">
      {{ (updated || created)?.slice(0, 10) }}
    </span>
    <span v-if="tags?.length" class="meta-tags">
      <a
        v-for="tag in tags"
        :key="tag"
        :href="withBase(`/tags#${encodeURIComponent(tag)}`)"
        class="meta-tag"
      >
        {{ tag }}
      </a>
    </span>
  </div>
</template>

<style scoped>
.doc-meta-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0 1rem;
  border-bottom: 1px solid var(--vp-c-divider);
  margin-bottom: 1.5rem;
  font-size: 0.85rem;
}

.meta-item a {
  color: var(--vp-c-brand-1);
  text-decoration: none;
  font-weight: 500;
}

.meta-item a:hover {
  text-decoration: underline;
}

.meta-item.date {
  color: var(--vp-c-text-3);
}

.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.meta-tag {
  display: inline-block;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  color: var(--vp-c-text-2);
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.78rem;
  text-decoration: none;
  transition: all 0.15s;
}

.meta-tag:hover {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}
</style>
