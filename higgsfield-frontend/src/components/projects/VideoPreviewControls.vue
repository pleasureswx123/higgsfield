<script setup lang="ts">
import { ref, computed } from 'vue'
import { IconPlayerPlayFilled, IconPlayerPauseFilled, IconVolume, IconVolumeOff, IconChevronDown } from '@tabler/icons-vue'
import { formatVideoTime } from '@/utils/videoTime'
import type { MediaComment } from '@/api/comments'
const props = defineProps<{ player?: HTMLVideoElement; time: number; duration: number; playing: boolean; comments: MediaComment[] }>()
const emit = defineEmits<{ select: [id: string]; seek: [time: number] }>()
const timecode = defineModel<boolean>('timecode', { default: false })
const rate = ref('1'), muted = ref(false), error = ref('')
const progress = computed(() => props.duration ? Math.min(100, props.time / props.duration * 100) : 0)
async function toggle() {
  if (!props.player) return
  error.value = ''
  if (!props.player.paused) props.player.pause()
  else try { await props.player.play() } catch { error.value = '视频暂时无法播放，请重试。' }
}
function changeRate() { if (props.player) props.player.playbackRate = Number(rate.value) }
function toggleMute() { if (props.player) { props.player.muted = !props.player.muted; muted.value = props.player.muted } }
</script>
<template>
  <section class="video-controls" aria-label="视频播放控制">
    <div class="video-timeline">
      <input aria-label="视频播放进度" type="range" min="0" :max="duration || 1" step="0.001" :value="time" :disabled="!duration" :style="{ '--progress': `${progress}%` }" @input="emit('seek', Number(($event.target as HTMLInputElement).value))" />
      <button v-for="row in comments" :key="row.id" class="timeline-comment" type="button" :style="{ left: `${Math.min(99, Math.max(1, Number(row.videoTime) / (duration || 1) * 100))}%` }" :title="`${formatVideoTime(row.videoTime || 0, timecode)} · ${row.author?.displayName || '评论'} · ${row.body}`" :aria-label="`定位评论 ${row.id}`" @click="emit('select', row.id)">{{ row.author?.displayName.slice(0, 1) || '评' }}</button>
    </div>
    <div class="video-control-row">
      <div class="video-play-actions">
        <button type="button" :aria-label="playing ? '暂停视频' : '播放视频'" @click="toggle"><IconPlayerPauseFilled v-if="playing" :size="19"/><IconPlayerPlayFilled v-else :size="19"/></button>
        <select v-model="rate" aria-label="播放速度" @change="changeRate"><option v-for="speed in ['0.5','0.75','1','1.25','1.5','2']" :key="speed" :value="speed">{{ speed }}×</option></select>
        <button type="button" :aria-label="muted ? '开启声音' : '静音'" @click="toggleMute"><IconVolumeOff v-if="muted" :size="20"/><IconVolume v-else :size="20"/></button>
      </div>
      <div class="video-time-display"><span>{{ formatVideoTime(time, timecode) }} / {{ formatVideoTime(duration, timecode) }}</span><select v-model="timecode" aria-label="时间格式"><option :value="false">标准时间</option><option :value="true">时间码</option></select><IconChevronDown :size="14"/></div>
      <div class="video-extra-actions"><slot /></div>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>
<style scoped>
.video-controls { flex-shrink:0; padding:14px 12px 10px; color:var(--foreground); }
.video-timeline { position:relative; height:46px; }
.video-timeline input { appearance:none; width:100%; height:5px; margin:0; display:block; border-radius:8px; background:linear-gradient(to right,var(--primary) var(--progress),var(--muted-foreground) var(--progress)); cursor:pointer; }
.video-timeline input::-webkit-slider-thumb { appearance:none; width:4px; height:12px; background:var(--foreground); border-radius:3px; }
.timeline-comment { position:absolute; top:13px; transform:translateX(-50%); display:grid;place-items:center; width:23px;height:23px;border:2px solid var(--foreground);border-radius:50%;background:var(--surface-raised);font-size:11px; }
.video-control-row { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:32px; }
.video-play-actions,.video-time-display,.video-extra-actions { display:flex; align-items:center; gap:10px; }
.video-time-display { position:relative; font-size:13px; }
.video-time-display select { position:absolute; inset:0; opacity:0; width:100%; cursor:pointer; }
button,select { color:inherit; background:transparent; border:0; cursor:pointer; }
select option { background:var(--surface); color:var(--foreground); }
button { display:flex; align-items:center; padding:3px; }
button:focus-visible,input:focus-visible,select:focus-visible { outline:2px solid var(--focus);outline-offset:3px; }
@media(max-width:600px) { .video-control-row { flex-wrap:wrap; } }
</style>
