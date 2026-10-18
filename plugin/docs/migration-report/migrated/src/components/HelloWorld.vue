<template>

  <div class="hello">
    <p>{{ message }}</p>
  </div>

</template>

<script setup>
import { ref } from 'vue';

defineProps({message: { type: String, default: 'Hello World' },})
const count = ref(0)
function increment() {
      count.value += 1;
      emit('update:count', count.value);
    }
const emit = defineEmits()
</script>