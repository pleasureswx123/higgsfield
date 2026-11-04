<script setup lang="ts">
defineProps<{ title: string; titleId: string; titleClass: string }>()
</script>

<template>
  <div class="dialog-heading">
    <h2 :id="titleId" :class="titleClass">{{ title }}</h2>
  </div>
</template>

<style scoped>
.dialog-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-right: 2rem;
}
.dialog-heading h2 {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
