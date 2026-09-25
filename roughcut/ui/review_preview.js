// Pure helpers are also exercised without a browser in the regression suite.
export function skipTarget(time, cuts, duration) {
  let target = time;
  for (const [start, end] of [...cuts].sort((a, b) => a[0] - b[0])) {
    if (target >= start && target < end) target = Math.min(end, duration);
  }
  return target;
}

export function editedTime(time, cuts) {
  let removed = 0, cursor = 0;
  for (const [start, end] of [...cuts].sort((a, b) => a[0] - b[0])) {
    removed += Math.max(0, Math.min(time, end) - Math.max(cursor, start));
    cursor = Math.max(cursor, end);
  }
  return Math.max(0, time - removed);
}

export default {
  props: { source: String, cuts: Array },
  data() { return { mode: 'original', frame: null, time: 0, duration: 0, error: '' }; },
  template: `
    <div class="w-full">
      <div class="row items-center q-gutter-sm q-mb-sm">
        <q-btn-toggle v-model="mode" no-caps dense toggle-color="teal"
          :options="[{label:'Original',value:'original'},{label:'Prévia dos cortes',value:'edited'}]" />
        <q-btn flat dense no-caps icon="replay" label="Do início" @click="restart" />
        <span class="text-caption">{{ clock(displayTime) }} / {{ clock(displayDuration) }}</span>
      </div>
      <video ref="video" :src="source" controls playsinline preload="metadata"
        style="width:100%;max-height:300px;background:#000;border-radius:8px"
        @play="start" @pause="stop" @ended="stop" @timeupdate="check"
        @seeked="check" @loadedmetadata="loaded" @error="error='Não foi possível reproduzir este codec no navegador.'" />
      <div class="text-caption text-grey-5 q-mt-xs">
        Prévia dos cortes sem gerar arquivo. Os saltos podem ter atraso de busca;
        efeitos de áudio e zoom não são simulados. A barra do player usa o tempo original.
      </div>
      <div v-if="error" role="alert" class="text-red-4">{{ error }}</div>
    </div>`,
  computed: {
    displayTime() { return this.mode === 'edited' ? editedTime(this.time, this.cuts) : this.time; },
    displayDuration() { return this.mode === 'edited' ? editedTime(this.duration, this.cuts) : this.duration; },
  },
  watch: {
    mode() { this.check(); },
    cuts: { deep: true, handler() { this.check(); } },
  },
  methods: {
    clock(value) { return `${Math.floor(value / 60)}:${(value % 60).toFixed(1).padStart(4, '0')}`; },
    loaded() { this.duration = this.$refs.video.duration || 0; this.error = ''; this.check(); },
    check() {
      const video = this.$refs.video;
      if (!video || !Number.isFinite(video.duration)) return;
      const next = this.mode === 'edited' ? skipTarget(video.currentTime, this.cuts, video.duration) : video.currentTime;
      if (next !== video.currentTime && !video.seeking) video.currentTime = next;
      this.time = video.currentTime;
    },
    start() {
      this.stop();
      const tick = () => {
        this.check();
        if (!this.$refs.video.paused && !this.$refs.video.ended) this.frame = requestAnimationFrame(tick);
      };
      tick();
    },
    stop() { if (this.frame !== null) cancelAnimationFrame(this.frame); this.frame = null; },
    restart() { this.$refs.video.currentTime = 0; this.check(); this.$refs.video.play().catch(() => {}); },
  },
  beforeUnmount() { this.stop(); if (this.$refs.video) this.$refs.video.pause(); },
};
