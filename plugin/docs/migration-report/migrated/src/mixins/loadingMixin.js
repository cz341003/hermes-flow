import { ref, onBeforeUnmount } from 'vue';

export function useLoading() {
  const loading = ref(false)
  function setLoading(v) {
      loading.value = v;
    }
  onBeforeUnmount(() => {})
  return { loading, setLoading }
}
