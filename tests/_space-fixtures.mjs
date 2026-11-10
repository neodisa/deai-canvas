/* Простори для JS-тестів без ключа `integrations` (4d-4c): роль — це `capabilities`, ЛІГА — це `compat`. */
export const NO_ROLES = { publish: null, tokens: null, comments: null, vcs: null, notify: null, dashboard: null, tracker: null };
export const plainSpace = (caps = {}) => ({ id: "p", name: "P", color: "space-1", capabilities: { ...NO_ROLES, ...caps } });
export const LIGA_SPACE = {
  id: "liga", name: "ЛІГА", color: "space-1",
  capabilities: { publish: "vercel-publish", tokens: null, comments: "supabase-comments", vcs: "git-sync", notify: "supabase-teams",
    dashboard: "supabase-dashboard", tracker: "jira-tracker" },
  compat: { publish: "design-canvas", vcs: "design-canvas", comments: "comment-layer" },
};
