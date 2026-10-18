<template>
  <div class="user-list">
    <a-table :data-source="users" :columns="columns" row-key="id">
      <template #action="{ record }">
        <a-button type="link" @click="editUser(record)">编辑</a-button>
      </template>
    </a-table>
  </div>
</template>

<script>
import { formatDate } from '../utils/format';

export default {
  name: 'UserList',
  data() {
    return {
      users: [
        { id: 1, name: '张三', createdAt: '2026-01-02T03:04:05Z' },
        { id: 2, name: '李四', createdAt: '2026-03-05T06:07:08Z' },
      ],
    };
  },
  computed: {
    columns() {
      return [
        { title: 'ID', dataIndex: 'id', key: 'id' },
        { title: '姓名', dataIndex: 'name', key: 'name' },
        { title: '创建时间', dataIndex: 'createdAt', key: 'createdAt' },
        { title: '操作', key: 'action', scopedSlots: { customRender: 'action' } },
      ];
    },
  },
  methods: {
    editUser(record) {
      this.$router.push({ name: 'about', query: { id: record.id } });
    },
  },
  filters: {
    date(s) {
      return formatDate(s);
    },
  },
};
</script>
