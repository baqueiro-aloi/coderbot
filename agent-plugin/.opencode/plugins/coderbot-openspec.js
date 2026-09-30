import path from 'path';
import { fileURLToPath } from 'url';
import { trustedConfig, trustedSessionPolicy } from '../../runtime/protocol.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const bridgeSkillsDir = path.resolve(__dirname, '../../skills');

export const CoderbotOpenSpecPlugin = async (input) => {
  const policy = input?.serverUrl ? trustedSessionPolicy(input) : null;
  const limit = Number(process.env.CODEBOT_MAX_SUBAGENTS || 3);
  let active = 0;
  const waiters = [];
  const assignments = new Set();
  return {
  ...(policy ? {
    event: policy.event,
    'chat.message': policy.before,
    'tool.execute.before': async (call, output) => {
      await policy.before(call);
      if (call.tool !== 'task') return;
      if (active >= limit) await new Promise(resolve => waiters.push(resolve));
      active++;
      assignments.add(call.callID);
    },
    'tool.execute.after': async (call) => {
      if (!assignments.delete(call.callID)) return;
      active--;
      waiters.shift()?.();
    },
  } : {}),
  config: async (config) => {
    trustedConfig(config);
    config.skills = config.skills || {};
    config.skills.paths = config.skills.paths || [];
    if (!config.skills.paths.includes(bridgeSkillsDir)) {
      config.skills.paths.push(bridgeSkillsDir);
    }
  },
  };
};
