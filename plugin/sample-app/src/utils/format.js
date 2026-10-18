export function formatDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function roleText(role) {
  const map = { admin: '管理员', guest: '访客', user: '用户' };
  return map[role] || role;
}
