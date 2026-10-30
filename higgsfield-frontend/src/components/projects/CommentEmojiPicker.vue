<script setup lang="ts">
import { computed, ref } from 'vue'
const emit = defineEmits<{ select: [emoji: string] }>()
const query = ref('')
const entries =
  '😀:开心笑脸 😃:高兴 😄:大笑 😁:露齿笑 😆:笑 😅:汗笑 😂:笑哭 🤣:大笑 😊:微笑 🙂:微笑 🙃:倒脸 😉:眨眼 😍:喜欢爱 🥰:爱 😘:亲吻 😋:美味 😎:酷 🤔:思考 😮:惊讶 😢:伤心 😭:哭 😡:生气 👍:赞 👎:反对 ❤️:爱心 🎉:庆祝 ✅:完成 👀:查看 🙏:感谢 🔥:火 💯:满分 🚀:火箭'
    .split(' ')
    .map((item) => {
      const [emoji, name] = item.split(':')
      return { emoji: emoji!, name: name! }
    })
const filtered = computed(() =>
  entries.filter((item) => (item.emoji + item.name).includes(query.value.trim())),
)
</script>
<template>
  <div class="comment-emoji-picker">
    <input v-model="query" placeholder="搜索表情" aria-label="搜索表情" />
    <div class="comment-emoji-grid">
      <button
        v-for="item in filtered"
        :key="item.emoji"
        :title="item.name"
        :aria-label="item.name"
        type="button"
        @click="emit('select', item.emoji)"
      >
        {{ item.emoji }}
      </button>
    </div>
    <p v-if="!filtered.length">没有匹配的表情</p>
  </div>
</template>
<style scoped>
.comment-emoji-picker {
  width: 100%;
  padding: 8px;
  border-radius: 16px;
  background: var(--surface-raised);
  color: var(--foreground);
}
input {
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 8px;
  outline: none;
}
.comment-emoji-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  max-height: 230px;
  overflow: auto;
  gap: 6px;
}
button {
  background: none;
  border: 0;
  border-radius: 8px;
  font-size: 24px;
  padding: 5px 0;
  cursor: pointer;
}
button:hover,
button:focus-visible {
  background: var(--surface-hover);
  outline: 1px solid var(--border);
}
p {
  text-align: center;
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
