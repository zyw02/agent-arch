#!/usr/bin/env python3
"""Launch the selected native CLI in a disposable user home; no scorer or gold."""
import json
import os
from pathlib import Path
import resource
import sys
import time
import uuid


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def launch(product, base, prompt):
    home = Path('/home/bench')
    env = dict(os.environ)
    # All of these are disposable relay credentials, never the real provider key.
    token = 'benchmark-relay-only'
    model = 'deepseek-flash'
    if product == 'openclaw57_patched' and os.environ.get('BENCH_AIOS_CONTEXT_MODEL') == 'deepseek-flash[1m]':
        model = 'deepseek-flash[1m]'
    max_output = int(os.environ.get('BENCH_MAX_OUTPUT_TOKENS', '16384'))
    iteration_limit = int(os.environ.get('BENCH_NATIVE_ITERATION_LIMIT', '64'))
    if product == 'dsh':
        env.update(DSH_HOME=str(home / '.dsh'), DEEPSEEK_BASE_URL=base + '/anthropic',
                   DEEPSEEK_API_KEY=token, DSH_PERMISSION_MODE='danger-full-access')
        overlay = home / 'dsh.patch.yml'
        write(overlay, f'''- id: llm-deepseek
  config:
    reasoningEffort: high
    maxTokens: {max_output}
- id: tool-web
  disabled: true
''')
        command = ['dsh', '--profile', 'headless', '--patch', str(overlay), '--json',
                   '--permission-mode', 'danger-full-access', '--approval-policy', 'never', prompt]
    elif product in ('openclaw', 'openclaw57_patched'):
        config = home / '.openclaw/openclaw.json'
        write(config, json.dumps(dict(
            gateway=dict(mode='local', auth=dict(mode='token', token=token)),
            models=dict(providers=dict(deepseek=dict(baseUrl=base + '/v1', apiKey=token,
                api='openai-completions', models=[dict(id=model, name='Frozen DeepSeek',
                    reasoning=True, input=['text'], contextWindow=1048576, maxTokens=max_output)]))),
            agents=dict(defaults=dict(workspace='/testbed', skipBootstrap=True,
                heartbeat=dict(every='0m'),
                model=dict(primary='deepseek/' + model), thinkingDefault='high')),
            tools=dict(profile='coding', exec=dict(mode='full'),
                       deny=['web_search', 'web_fetch', 'browser', 'memory_search', 'memory_get']),
            cron=dict(enabled=False))))
        env.update(OPENCLAW_STATE_DIR=str(config.parent), OPENCLAW_CONFIG_PATH=str(config),
                   OPENCLAW_SKIP_CHANNELS='1')
        if os.environ.get('BENCH_TASK_TIMEOUT_SECONDS'):
            settings = json.loads(config.read_text())
            settings['agents']['defaults']['timeoutSeconds'] = int(os.environ['BENCH_TASK_TIMEOUT_SECONDS'])
            write(config, json.dumps(settings))
        command = ['openclaw', 'agent', '--local', '--session-id', str(uuid.uuid5(uuid.NAMESPACE_URL, os.environ['BENCH_RUN_ID'])),
                   '--json', '--message', prompt]
        if product == 'openclaw57_patched':
            # The older schema expresses the same unrestricted local execution
            # policy as security/ask. Run this source build explicitly: its
            # mobile entrypoint shebang must not select the system openclaw.
            settings = json.loads(config.read_text())
            settings['tools']['exec'] = dict(security='full', ask='off')
            if os.environ.get('BENCH_AIOS_RUNTIME') == 'agentloop':
                settings['agents']['defaults']['agentRuntime'] = dict(id='agentloop')
                settings['agents']['defaults']['memorySearch'] = dict(enabled=False)
                settings['agents']['defaults']['timeoutSeconds'] = int(os.environ['BENCH_TASK_TIMEOUT_SECONDS'])
                settings['plugins'] = dict(entries=dict(agentloop=dict(enabled=True)))
                settings['logging'] = dict(level='debug', consoleLevel='info',
                                           file='/home/bench/agentloop-debug.log')
                env.update(OPENCLAW_AGENT_RUNTIME='agentloop', AGENTLOOP_WARMUP='0')
                if os.environ.get('BENCH_NATIVE_ITERATION_LIMIT'):
                    env['AGENTLOOP_LOOP_MAX_TURNS'] = str(iteration_limit)
            write(config, json.dumps(settings))
            command = ['node', '/opt/openclaw57/openclaw.mjs', *command[1:]]
    elif product == 'claude':
        env.update(ANTHROPIC_BASE_URL=base + '/anthropic', ANTHROPIC_AUTH_TOKEN=token,
                   ANTHROPIC_API_KEY=token, ANTHROPIC_MODEL=model,
                   ANTHROPIC_DEFAULT_OPUS_MODEL=model, ANTHROPIC_DEFAULT_SONNET_MODEL=model,
                   ANTHROPIC_DEFAULT_HAIKU_MODEL=model, ANTHROPIC_DEFAULT_FABLE_MODEL=model,
                   ANTHROPIC_CUSTOM_MODEL_OPTION=model,
                   ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES='effort,thinking,adaptive_thinking,interleaved_thinking',
                   CLAUDE_CODE_MAX_CONTEXT_TOKENS='1048576', CLAUDE_CODE_SUBAGENT_MODEL=model,
                   CLAUDE_CODE_EFFORT_LEVEL='high', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
                   CLAUDE_CODE_DISABLE_AUTO_MEMORY='1', DISABLE_AUTOUPDATER='1')
        write(home / '.claude.json', json.dumps(dict(hasCompletedOnboarding=True)))
        command = ['claude', '-p', '--verbose', '--output-format', 'stream-json',
                   '--permission-mode', 'bypassPermissions', '--model', model,
                   '--disallowedTools', 'WebSearch,WebFetch', '--', prompt]
    elif product == 'codex':
        env.update(BENCH_API_KEY=token)
        write(home / '.codex/config.toml', f'''model = "{model}"
model_provider = "bench"
model_reasoning_effort = "high"
web_search = "disabled"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_context_window = 1048576
[model_providers.bench]
name = "Frozen DeepSeek"
base_url = "{base}/v1"
env_key = "BENCH_API_KEY"
wire_api = "responses"
requires_openai_auth = false
''')
        command = ['codex', 'exec', '--json', '--skip-git-repo-check',
                   '--dangerously-bypass-approvals-and-sandbox', prompt]
    elif product == 'hermes':
        root = home / '.hermes'
        env.update(HERMES_HOME=str(root), DEEPSEEK_API_KEY=token,
                   DEEPSEEK_BASE_URL=base + '/v1', HERMES_YOLO_MODE='1',
                   TERMINAL_CWD='/testbed', TERMINAL_ENV='local')
        write(root / 'config.yaml', f'''model:
  default: {model}
  provider: deepseek
  base_url: {base}/v1
  api_key: {token}
agent:
  max_turns: {iteration_limit}
  reasoning_effort: high
terminal:
  backend: local
  cwd: /testbed
memory:
  memory_enabled: false
  user_profile_enabled: false
''')
        command = ['/opt/hermes-venv/bin/hermes', '-z', prompt, '--model', model,
                   '--provider', 'deepseek', '--reasoning', 'high', '--toolsets', 'terminal,file,todo,delegation,code_execution',
                   '--usage-file', str(home / 'native-usage.json')]
    else:
        raise ValueError('Unknown product')
    # The actual credential never enters this process or the container.
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    product, base, prompt_file = sys.argv[1:]
    prompt = Path(prompt_file).read_text()
    started = time.monotonic_ns()
    pid = os.fork()
    if pid == 0:
        launch(product, base, prompt)
        os._exit(127)
    _, status, usage = os.wait4(pid, 0)
    report = dict(agent_started_ns=started, agent_ended_ns=time.monotonic_ns(),
                  exit_code=os.waitstatus_to_exitcode(status),
                  direct_child_rusage=dict(user_seconds=usage.ru_utime, system_seconds=usage.ru_stime,
                                           maxrss_kib=usage.ru_maxrss, block_in=usage.ru_inblock, block_out=usage.ru_oublock))
    write(Path('/home/bench/agent-exit.json'), json.dumps(report))
    # Keep the cgroup alive for final cpu.stat, memory.peak and io.stat reads.
    # The host freezes the container immediately after observing this file.
    while True:
        time.sleep(3600)
