<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElInput, ElAlert } from 'element-plus'
import { IconLock, IconUsers } from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import { useCreateProject } from '@/composables/useCreateProject'
const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [id: string] }>()
const { form, name, pending, error, rules, submit } = useCreateProject(open, (id) =>
  emit('created', id),
)
</script>
<template>
  <ElDialog
    v-model="open"
    title="新建项目"
    width="480px"
    align-center
    class="create-project-dialog"
    :close-on-click-modal="false"
    :close-on-press-escape="!pending"
    :show-close="!pending"
    :before-close="
      (done) => {
        if (!pending) done()
      }
    "
    destroy-on-close
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="新建项目" />
    </template>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <ElForm ref="form" :model="{ name }" :rules="rules" @submit.prevent="submit"
      ><ElFormItem prop="name" label="项目名称" class="project-name-field"
        ><ElInput
          v-model="name"
          placeholder="我的项目"
          maxlength="200"
          :disabled="pending"
          autofocus
          aria-label="项目名称"
      /></ElFormItem>
      <div class="project-privacy"><IconLock :size="14" />仅项目成员可访问</div>
      <div class="project-create-note">
        <IconUsers :size="22" /><span
          >你将成为这个项目的首位负责人。<small>项目空间将与项目同时创建。</small></span
        >
      </div>
      <Button type="submit" class="project-create-submit" :disabled="pending">{{
        pending ? '正在创建…' : '创建项目'
      }}</Button></ElForm
    >
  </ElDialog>
</template>
