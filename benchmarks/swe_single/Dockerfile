FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM node:24.22.1-bookworm-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_CACHE_DIR=/tmp/uv-cache
RUN apt-get update -qq && apt-get install -y --no-install-recommends git ca-certificates curl ripgrep zstd time procps python3 build-essential && rm -rf /var/lib/apt/lists/*
RUN uv python install 3.9.20 3.14.0
RUN npm install --prefix /opt/products --save-exact --no-audit --no-fund --dangerously-allow-all-scripts @deepseek-ai/dsh@0.2.2-rc.1 openclaw@2026.11.3 @openai/codex@0.167.1 @anthropic-ai/claude-code@2.1.322
RUN git clone --filter=blob:none --no-checkout https://github.com/NousResearch/hermes-agent.git /opt/hermes && git -C /opt/hermes checkout 84a0301415edd6d1385207ec96e4d7f2b6c1fcd9 && cd /opt/hermes && UV_PROJECT_ENVIRONMENT=/opt/hermes-venv uv sync --frozen --no-dev --extra anthropic --python 3.14.0 && rm -rf /opt/hermes/.git
RUN uv venv --seed /opt/testenv --python 3.9.20 && uv pip install --python /opt/testenv/bin/python setuptools==75.1.0 wheel==0.44.0 setuptools-scm==8.1.0 atomicwrites==1.4.1 attrs==23.1.0 more-itertools==10.1.0 packaging==23.1 pluggy==0.13.1 py==1.11.0 wcwidth==0.2.6 six==1.16.0 hypothesis==6.56.4 iniconfig==1.1.1 toml==0.10.2
COPY task-source /testbed
RUN cd /testbed && SETUPTOOLS_SCM_PRETEND_VERSION=6.0.0rc1 uv pip install --python /opt/testenv/bin/python --no-deps --no-build-isolation -e . && /opt/testenv/bin/python -m pip freeze > /opt/test-dependencies.txt
RUN printf '%s\n' '#!/bin/sh' 'exec /opt/testenv/bin/python "$@"' > /usr/local/bin/python && chmod +x /usr/local/bin/python && ln -s python /usr/local/bin/python3 && ln -s /opt/testenv/bin/pytest /usr/local/bin/pytest
COPY agent_entry.py /opt/bench/agent_entry.py
RUN usermod --login bench --home /home/bench --move-home node && groupmod --new-name bench node && chown -R bench:bench /testbed /home/bench && chmod -R a+rX /opt/python /opt/hermes /opt/hermes-venv /opt/products /opt/testenv
ENV HOME=/home/bench PATH=/opt/testenv/bin:/opt/products/node_modules/.bin:/usr/local/bin:/usr/bin:/bin PYTHONPATH=/testbed/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
WORKDIR /testbed
ENTRYPOINT ["python3", "/opt/bench/agent_entry.py"]
