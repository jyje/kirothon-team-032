<script setup lang="ts">
import { computed, ref } from 'vue'
import { api, ApiError } from '@/api'
import type { Asset } from '@/types'

type Point = { x: number; y: number }
type Region = { left: number; top: number; right: number; bottom: number }
type Review = { revision: string; regions: Region[]; detection_available: boolean }

const props = defineProps<{ path: string; photo: Asset }>()
const emit = defineEmits<{ saved: [photo: Asset] }>()
const details = ref<HTMLDetailsElement>()
const review = ref<Review>()
const regions = ref<Region[]>([])
const start = ref<Point>()
const end = ref<Point>()
const pointer = ref<number>()
const imageReady = ref(false)
const busy = ref(false)
const error = ref('')
const maxRegions = 100
const edges = [
  { field: 'left', name: '왼쪽' }, { field: 'top', name: '위' },
  { field: 'right', name: '오른쪽' }, { field: 'bottom', name: '아래' },
] as const
const drawing = computed(() => start.value && end.value ? rectangle(start.value, end.value) : null)

function rectangle(a: Point, b: Point): Region {
  return {
    left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
    right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y),
  }
}

function location(event: PointerEvent): Point {
  const {left, top, width, height} = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return {
    x: Math.round(100 * Math.min(1, Math.max(0, (event.clientX - left) / width))),
    y: Math.round(100 * Math.min(1, Math.max(0, (event.clientY - top) / height))),
  }
}

function startArea(event: PointerEvent) {
  if (!imageReady.value || busy.value || event.button !== 0 || pointer.value !== undefined ||
      regions.value.length >= maxRegions) return
  pointer.value = event.pointerId
  const surface = event.currentTarget as HTMLElement
  surface.setPointerCapture(event.pointerId)
  start.value = end.value = location(event)
}

function moveArea(event: PointerEvent) {
  if (pointer.value === event.pointerId) end.value = location(event)
}

function cancelArea() {
  pointer.value = undefined
  start.value = end.value = undefined
}

function finishArea(event: PointerEvent) {
  if (pointer.value !== event.pointerId) return
  moveArea(event)
  const box = drawing.value
  if (box && box.right > box.left && box.bottom > box.top) regions.value.push(box)
  cancelArea()
}

function areaStyle(area: Region) {
  return {
    left: area.left + '%', top: area.top + '%',
    width: (area.right - area.left) + '%', height: (area.bottom - area.top) + '%',
  }
}

async function load() {
  if (busy.value) return
  busy.value = true
  imageReady.value = false
  error.value = ''
  try {
    review.value = await api<Review>(props.path + '/face-review')
    regions.value = review.value.regions.map(box => ({
      left: Math.floor(box.left * 100), top: Math.floor(box.top * 100),
      right: Math.ceil(box.right * 100), bottom: Math.ceil(box.bottom * 100),
    }))
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '얼굴 확인을 열지 못했어요.'
  } finally {
    busy.value = false
  }
}

function openReview() {
  if (details.value?.open && !review.value) void load()
}

async function save() {
  if (!review.value || !imageReady.value || busy.value) return
  if (regions.value.some(box => box.left >= box.right || box.top >= box.bottom)) {
    error.value = '영역의 왼쪽과 위 값은 오른쪽과 아래 값보다 작아야 해요.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const saved = await api<Asset>(props.path + '/face-review', {
      method: 'PUT',
      json: {
        revision: review.value.revision,
        regions: regions.value.map(box => ({
          left: box.left / 100, top: box.top / 100, right: box.right / 100, bottom: box.bottom / 100,
        })),
      },
    })
    emit('saved', saved)
    review.value = undefined
    if (details.value) details.value.open = false
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : '사진을 저장하지 못했어요.'
    if (cause instanceof ApiError && cause.status === 409) review.value = undefined
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <details ref="details" @toggle="openReview">
    <summary>{{ photo.faces_blurred ? '얼굴 흐림 적용됨' : photo.face_check_confirmed ? '얼굴 확인 완료' : '얼굴 확인' }}</summary>
    <p v-if="error" class="review-error" role="alert">{{ error }}</p>
    <p v-if="busy" role="status">사진을 처리하는 중이에요.</p>
    <button v-if="!review && !busy && error" type="button" class="btn btn-small" @click="load">다시 불러오기</button>
    <form v-if="review" class="review" @submit.prevent="save">
      <p v-if="!review.detection_available">자동 탐지를 사용할 수 없어요. 확인이 필요한 부분을 직접 추가해 주세요.</p>
      <p v-else-if="!regions.length">선택한 영역이 없어요. 사진을 확인하고 필요하면 영역을 추가해 주세요.</p>
      <p v-else>사진을 확인하고 흐릴 영역을 조정해 주세요.</p>
      <div
        class="review-image"
        :class="{ ready: imageReady }"
        @pointerdown="startArea"
        @pointermove="moveArea"
        @pointerup="finishArea"
        @pointercancel="cancelArea"
        @lostpointercapture="cancelArea"
      >
        <img :src="`${path}/file?review=${review.revision}`" :alt="`${photo.display_name} 검토용 사진`" draggable="false" @load="imageReady = true" @error="error = '검토할 사진을 불러오지 못했어요.'" />
        <div v-for="(box, index) in regions" :key="index" class="face-box" :style="areaStyle(box)" aria-hidden="true">{{ index + 1 }}</div>
        <div v-if="drawing" class="face-box" :style="areaStyle(drawing)" aria-hidden="true"></div>
      </div>
      <fieldset v-for="(box, index) in regions" :key="index" :disabled="busy">
        <legend>영역 {{ index + 1 }}</legend>
        <label v-for="edge in edges" :key="edge.field">
          {{ edge.name }} (%)
          <input v-model.number="box[edge.field]" type="number" min="0" max="100" required />
        </label>
        <button type="button" class="btn btn-small" :aria-label="`영역 ${index + 1} 제거`" @click="regions.splice(index, 1)">영역 제거</button>
      </fieldset>
      <div class="review-actions">
        <button type="button" class="btn btn-small" :disabled="busy || regions.length >= maxRegions" @click="regions.push({ left: 25, top: 25, right: 75, bottom: 75 })">영역 추가</button>
        <button type="submit" class="btn btn-small" :disabled="busy || !imageReady">{{ regions.length ? '흐림 적용' : '확인 완료' }}</button>
      </div>
    </form>
  </details>
</template>

<style scoped>
summary { cursor: pointer; font-weight: 700; }
p { margin: 0; }
.review { display: grid; gap: var(--space-3); margin-block: var(--space-2); }
.review-image { position: relative; max-inline-size: 42rem; }
.review-image.ready { cursor: crosshair; touch-action: none; }
.review-image img { display: block; width: 100%; height: auto; }
.face-box {
  position: absolute;
  pointer-events: none;
  border: var(--border);
  border-color: var(--color-kiro);
  outline: 1px solid var(--color-white);
  overflow: hidden;
  color: var(--color-white);
  text-shadow: 1px 1px var(--color-ink);
}
fieldset {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
  min-inline-size: 0;
  margin: 0;
  padding: var(--space-2);
}
fieldset label { display: grid; gap: var(--space-1); }
fieldset input { width: 100%; min-inline-size: 0; }
fieldset button { grid-column: 1 / -1; justify-self: start; }
.review-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
</style>
