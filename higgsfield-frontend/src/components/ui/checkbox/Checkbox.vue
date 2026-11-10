<script setup lang="ts">
import type { CheckboxRootEmits, CheckboxRootProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { IconCheck as Check, IconMinus as Minus } from "@tabler/icons-vue"
import { CheckboxIndicator, CheckboxRoot, useForwardPropsEmits } from "reka-ui"
import { cn } from "@/utils/cn"

const props = defineProps<CheckboxRootProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<CheckboxRootEmits>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <CheckboxRoot
    v-slot="{ state }"
    data-slot="checkbox"
    v-bind="forwarded"
    :class="
      cn('grid place-content-center peer h-4 w-4 shrink-0 rounded-sm border border-muted-foreground/50 bg-transparent shadow-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground',
         props.class)"
  >
    <CheckboxIndicator class="grid place-content-center text-current">
      <slot>
        <Minus v-if="state === 'indeterminate'" class="h-4 w-4" />
        <Check v-else class="h-4 w-4" />
      </slot>
    </CheckboxIndicator>
  </CheckboxRoot>
</template>

<style scoped>
/* 基础按钮样式位于工具类层之外，在组件内统一映射选中状态的主题色。 */
[data-slot="checkbox"][data-state="checked"],
[data-slot="checkbox"][data-state="indeterminate"] {
  color: var(--primary-foreground);
}
</style>
