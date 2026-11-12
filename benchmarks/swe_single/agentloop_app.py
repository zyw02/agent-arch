"""Supply the SDK's native default complex-loop application configuration."""
import json
from pathlib import Path


def prepare_default_app(home):
    # The delivery contains no bundled Apps. Its documented user Apps directory
    # is configuration, not a custom executor or benchmark-specific prompt.
    app = Path(home)/'.openclaw/agentloop/apps/default'
    app.mkdir(parents=True, exist_ok=True)
    manifest = dict(app_name='default', loop_mode=[dict(id='main', type='complex')])
    (app/'agent.app.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (app/'index.js').write_text('export {};\n')
    return app.parent
