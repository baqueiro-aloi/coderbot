import path from 'path';
import { fileURLToPath } from 'url';
import { trustedConfig, trustedSessionPolicy } from '../../runtime/protocol.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const bridgeSkillsDir = path.resolve(__dirname, '../../skills');

export const CoderbotOpenSpecPlugin = async (input) => {
  const policy = input?.serverUrl ? trustedSessionPolicy(input) : null;
  return {
  ...(policy ? {
    event: policy.event,
    'chat.message': policy.before,
    'tool.execute.before': policy.before,
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
