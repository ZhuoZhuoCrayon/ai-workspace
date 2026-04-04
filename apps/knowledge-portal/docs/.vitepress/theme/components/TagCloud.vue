<script setup lang="ts">
import { computed } from 'vue'
import { withBase } from 'vitepress'

const props = defineProps<{
  tags: Record<string, { title: string; path: string; project: string }[]>
  limit?: number
}>()

const sortedTags = computed(() => {
  const entries = Object.entries(props.tags)
    .sort((a, b) => b[1].length - a[1].length)
  return props.limit ? entries.slice(0, props.limit) : entries
})

const maxCount = computed(() => {
  if (sortedTags.value.length === 0) return 1
  return sortedTags.value[0][1].length
})

function fontSize(count: number): string {
  const min = 0.78
  const max = 1.3
  const scale = Math.min(count / maxCount.value, 1)
  return `${min + scale * (max - min)}rem`
}
</script>

<template>
  <div class="tag-cloud">
    <a
      v-for="[tag, docs] in sortedTags"
      :key="tag"
      :href="withBase(`tags#${tag}`)"
      class="tag-chip"
      :style="{ fontSize: fontSize(docs.length) }"
    >
      {{ tag }}
      <sup>{{ docs.length }}</sup>
    </a>
  </div>
</template>

<style scoped>
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}

.tag-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 0.15rem;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-2);
  border: 1px solid var(--vp-c-divider);
  border-radius: 999px;
  padding: 0.25rem 0.7rem;
  text-decoration: none;
  white-space: nowrap;
  transition: all 0.2s ease;
  line-height: 1.5;
}

.tag-chip:hover {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  border-color: var(--vp-c-brand-1);
}

.tag-chip sup {
  font-size: 0.65em;
  color: var(--vp-c-text-3);
}
</style>
