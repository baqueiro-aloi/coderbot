// OpenCode 1.18.18 HTTP/event contract. No private runtime modules required.
export const RUNTIME_VERSION = '1.18.18';
export const TRUSTED_PERMISSION = [{ permission: '*', pattern: '*', action: 'allow' }];

export function trustedConfig(config) {
  config.permission = 'allow';
  config.agent ||= {};
  for (const name of new Set(['build', 'plan', 'general', 'explore', ...Object.keys(config.agent)])) {
    config.agent[name] = { ...config.agent[name], permission: 'allow' };
  }
  return config;
}

export function permissionRequest(event) {
  if (event?.type !== 'permission.asked') return null;
  const p = event.properties;
  if (!p?.id || !p?.sessionID) throw new Error('Invalid permission.asked event');
  return { sessionID: p.sessionID, permissionID: p.id, response: 'always' };
}
