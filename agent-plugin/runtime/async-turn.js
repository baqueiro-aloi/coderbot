// Keep HTTP requests short even when an agent turn runs for many minutes.
export async function runAsyncTurn(request, sessionID, body, {sleep = ms =>
  new Promise(resolve => setTimeout(resolve, ms)), failure = () => null} = {}) {
  const route = `/session/${sessionID}`;
  const before = await (await request(`${route}/message`)).json();
  const previous = new Set(before.map(message => message.info.id));
  await request(`${route}/prompt_async`, 'POST', body);
  while (true) {
    if (failure()) throw new Error('OpenCode session failed');
    const statuses = await (await request('/session/status')).json();
    if (!statuses[sessionID] || statuses[sessionID].type === 'idle') {
      const history = await (await request(`${route}/message`)).json();
      const messages = history.filter(message => !previous.has(message.info.id));
      const assistant = messages.filter(message => message.info.role === 'assistant');
      const last = assistant.at(-1);
      if (last?.info.error) throw new Error(JSON.stringify(last.info.error));
      // Initial idle is not completion; tool-call steps are not a final answer.
      if (last?.info.time?.completed && last.info.finish &&
          !['tool-calls', 'unknown'].includes(last.info.finish)) return messages;
    }
    await sleep(1000);
  }
}
