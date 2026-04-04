<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  data: Record<string, number>
}>()

const weeks = computed(() => {
  const today = new Date()
  const daysBack = 365
  const start = new Date(today)
  start.setDate(start.getDate() - daysBack)

  const dayOfWeek = start.getDay()
  start.setDate(start.getDate() - dayOfWeek)

  const result: { date: string; count: number; level: number }[][] = []
  let currentWeek: { date: string; count: number; level: number }[] = []

  const cursor = new Date(start)
  while (cursor <= today) {
    const dateStr = cursor.toISOString().slice(0, 10)
    const count = props.data[dateStr] ?? 0
    const level = count === 0 ? 0 : count <= 1 ? 1 : count <= 3 ? 2 : count <= 5 ? 3 : 4

    currentWeek.push({ date: dateStr, count, level })
    if (currentWeek.length === 7) {
      result.push(currentWeek)
      currentWeek = []
    }
    cursor.setDate(cursor.getDate() + 1)
  }
  if (currentWeek.length > 0) result.push(currentWeek)

  return result
})

const months = computed(() => {
  const labels: { text: string; col: number }[] = []
  let prevMonth = ''
  for (let w = 0; w < weeks.value.length; w++) {
    const firstDay = weeks.value[w][0]
    if (!firstDay) continue
    const month = firstDay.date.slice(0, 7)
    if (month !== prevMonth) {
      const d = new Date(firstDay.date)
      labels.push({ text: `${d.getMonth() + 1}月`, col: w })
      prevMonth = month
    }
  }
  return labels
})

</script>

<template>
  <div class="activity-calendar">
    <div class="calendar-months">
      <span
        v-for="m in months"
        :key="m.col"
        class="month-label"
        :style="{ gridColumnStart: m.col + 1 }"
      >
        {{ m.text }}
      </span>
    </div>
    <div class="calendar-grid">
      <div v-for="(week, wi) in weeks" :key="wi" class="calendar-col">
        <div
          v-for="day in week"
          :key="day.date"
          class="cell"
          :data-level="day.level"
          :title="`${day.date}: ${day.count} 篇`"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity-calendar {
  overflow-x: auto;
  padding-bottom: 0.2rem;
}

.calendar-months {
  display: grid;
  grid-auto-columns: 14px;
  grid-auto-flow: column;
  gap: 3px;
  margin-bottom: 5px;
  font-size: 0.68rem;
  color: color-mix(in srgb, var(--vp-c-text-3) 88%, transparent);
}

.calendar-grid {
  display: flex;
  gap: 3px;
}

.calendar-col {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.cell {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--vp-c-bg-soft);
  border: 1px solid color-mix(in srgb, var(--vp-c-divider) 38%, transparent);
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}

.cell:hover {
  transform: translateY(-1px) scale(1.04);
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.2);
}

.cell[data-level="1"] { background: #9be9a8; }
.cell[data-level="2"] { background: #40c463; }
.cell[data-level="3"] { background: #30a14e; }
.cell[data-level="4"] { background: #216e39; }

:root.dark .cell[data-level="0"] { background: var(--vp-c-bg-alt); }
:root.dark .cell[data-level="1"] { background: #0e4429; }
:root.dark .cell[data-level="2"] { background: #006d32; }
:root.dark .cell[data-level="3"] { background: #26a641; }
:root.dark .cell[data-level="4"] { background: #39d353; }
</style>
