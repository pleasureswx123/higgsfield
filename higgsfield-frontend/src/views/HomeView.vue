<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import RecentProjects from '@/components/projects/RecentProjects.vue'
const auth = useAuthStore()
const nickname = computed(() => auth.user?.user.nickName?.trim() || '')
</script>

<template>
  <div class="home-page project-home">
    <header class="project-home-heading">
      <div class="welcome-copy">
        <span class="welcome-brand">Nightmare Theatre</span>
        <h1>欢迎回来<span v-if="nickname">，{{ nickname }}</span></h1>
        <p>让你的下一个故事，从这里开始。</p>
      </div>
      <div class="welcome-decoration" aria-hidden="true"></div>
    </header>
    <RecentProjects />
  </div>
</template>

<style scoped>
.project-home { padding-top: 12px; }
.project-home-heading { position:relative; isolation:isolate; display:flex; align-items:center; min-height:164px; padding:24px 0 30px; margin-bottom:28px; border-bottom:1px solid var(--border); overflow:hidden; }
.welcome-copy { position:relative; z-index:1; max-width:100%; }
.welcome-brand { display:block; margin-bottom:16px; font-size:10px; line-height:1.4; letter-spacing:0.24em; color:var(--muted-foreground); }
.project-home-heading h1 { margin: 0 0 10px; font-size: 30px; line-height:1.4; font-weight: 650; letter-spacing:-0.025em; overflow-wrap:anywhere; color: var(--foreground); }
.project-home-heading p { margin: 0; font-size: 13px; line-height: 1.6; color: var(--muted-foreground); }
.welcome-decoration { position:absolute; z-index:0; pointer-events:none; width:340px; height:200px; right:-70px; top:-50px; border-radius:50%; background:radial-gradient(ellipse, color-mix(in srgb, var(--primary) 7%, transparent), transparent 68%); }
.welcome-decoration::after { content:''; position:absolute; inset:32px 20px; border:1px solid color-mix(in srgb, var(--muted-foreground) 12%, transparent); border-radius:50%; transform:rotate(-24deg); }
@media (max-width: 760px) {
  .project-home { padding-top: 4px; }
  .project-home-heading { min-height:148px; padding:20px 0 24px; margin-bottom:24px; }
  .project-home-heading h1 { font-size: 24px; }
  .welcome-decoration { opacity:0.5; right:-190px; }
}
</style>
