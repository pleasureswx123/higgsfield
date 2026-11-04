<script setup lang="ts">
import type { PrimitiveProps } from 'reka-ui'
import { Button as ShadcnButton } from '@/components/ui/button'
import { cva } from 'class-variance-authority'
import { cn } from '@/utils/cn'
import type { HTMLAttributes } from 'vue'
const props = withDefaults(
  defineProps<
    PrimitiveProps & { variant?: 'default' | 'ghost' | 'outline'; class?: HTMLAttributes['class'] }
  >(),
  { as: 'button', variant: 'default', class: undefined },
)
const variants = cva('ui-button', {
  variants: {
    variant: {
      default: 'ui-button-primary',
      ghost: 'ui-button-ghost',
      outline: 'ui-button-outline',
    },
  },
})
</script>
<template>
  <ShadcnButton :variant="variant" :as="as" :as-child="asChild" :class="cn(variants({ variant }), props.class)"
    ><slot
  /></ShadcnButton>
</template>
