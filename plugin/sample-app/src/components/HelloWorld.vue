<template>
  <div class="hello">
    <p>{{ message }}</p>
  </div>
</template>

<script>
export default {
  name: 'HelloWorld',
  props: {
    message: { type: String, default: 'Hello World' },
  },
  data() {
    return { count: 0 };
  },
  methods: {
    increment() {
      this.count += 1;
      this.$emit('update:count', this.count);
    },
  },
};
</script>
