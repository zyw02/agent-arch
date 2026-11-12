#!/usr/bin/env python3
"""Extend the frozen five-product environment with the exact supplied patch."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from sealed_input import transform

HERE = Path(__file__).resolve().parent
INPUTS = HERE / 'inputs'
SDK = 'zte-agentloop-sdk-6.26.20-b4.tgz'


def digest(path, algorithm='sha256'):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def verify_vendor(path, expected_integrity):
    with Path(path).open('rb') as stream:
        actual = base64.b64encode(hashlib.file_digest(stream, 'sha512').digest()).decode()
    if 'sha512-' + actual != expected_integrity:
        raise ValueError('Vendor SDK differs from the patch lockfile integrity: expected '
                         + expected_integrity + ', actual sha512-' + actual)
    with tarfile.open(path) as archive:
        package = json.load(archive.extractfile('package/package.json'))
    if package['name'] != '@zte/agentloop-sdk':
        raise ValueError('Wrong vendor SDK package')


def require_inputs(manifest):
    for name, expected in manifest['sealed_inputs'].items():
        path = INPUTS / name
        if not path.is_file():
            raise FileNotFoundError(f'Required build input missing: {name}; do not omit the SDK or change dependencies')
        if digest(path) != expected:
            raise ValueError(f'Build input checksum mismatch: {name}')
    if 'agentloop-sdk.tgz.enc' not in manifest['sealed_inputs']:
        raise FileNotFoundError(f'Required vendor package {SDK} has not been supplied; no model runs admitted')
    for name, field in (
        ('reference-package-lock.json', 'reference_package_lock_sha256'),
        ('reference-test-dependencies.txt', 'reference_test_dependencies_sha256'),
    ):
        if digest(INPUTS / name) != manifest[field]:
            raise ValueError(f'Historical environment lock changed: {name}')


def prepare(output, diagnose_sdk=False):
    manifest = json.loads((INPUTS / 'source.json').read_text())
    # Fail before fetching or building if the exact vendor artifact is absent.
    require_inputs(manifest)
    subprocess.run(['python3', str(HERE / 'prepare.py'), '--output', str(output)], check=True)
    context = output / 'context'
    with tempfile.TemporaryDirectory(prefix='enhanced-source-', dir=output) as temporary:
        temporary = Path(temporary)
        delivery = temporary / 'pchs.tar.gz'
        transform(INPUTS / 'pchs.tar.gz.enc', delivery, decrypt=True)
        if digest(delivery) != manifest['delivery_sha256']:
            raise ValueError('Decrypted delivery does not match the supplied archive')
        with tarfile.open(delivery) as archive:
            archive.extractall(temporary, filter='data')
        patch = temporary / 'pchs' / manifest['patch_filename']
        if digest(patch) != manifest['patch_sha256']:
            raise ValueError('Patch checksum mismatch')
        checkout = temporary / 'source'
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'fetch', '--depth', '1',
                        'https://github.com/openclaw/openclaw.git', manifest['baseline_commit']], check=True)
        subprocess.run(['git', '-C', str(checkout), 'checkout', '--detach', '-q', 'FETCH_HEAD'], check=True)
        tree = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
        if tree != manifest['baseline_tree']:
            raise ValueError('Upstream baseline tree mismatch')
        subprocess.run(['git', '-C', str(checkout), 'apply', '--index', '--whitespace=nowarn', str(patch)], check=True)
        tree = subprocess.check_output(['git', '-C', str(checkout), 'write-tree'], text=True).strip()
        if tree != manifest['patched_tree']:
            raise ValueError('Applied patch tree differs from the supplied target')
        snapshot = temporary / 'patched.tar'
        subprocess.run(['git', '-C', str(checkout), 'archive', '-o', str(snapshot), tree], check=True)
        source = context / 'enhanced-source'
        source.mkdir()
        with tarfile.open(snapshot) as archive:
            archive.extractall(source, filter='data')
        sdk = source / 'extensions/agentloop' / SDK
        transform(INPUTS / 'agentloop-sdk.tgz.enc', sdk, decrypt=True)
        vendor_sha = digest(sdk)
        if vendor_sha != manifest['sdk_sha256']:
            raise ValueError('Restored SDK does not match the new delivery SHA-256')
        verify_vendor(sdk, manifest['sdk_delivery_integrity'])
        sdk_matches_lock = True
        try:
            verify_vendor(sdk, manifest['sdk_integrity'])
        except ValueError:
            sdk_matches_lock = False
            if not diagnose_sdk and 'pnpm-lock.yaml.enc' not in manifest['sealed_inputs']:
                raise
        if not diagnose_sdk and 'pnpm-lock.yaml.enc' in manifest['sealed_inputs']:
            updated_lock = source / 'pnpm-lock.yaml'
            transform(INPUTS / 'pnpm-lock.yaml.enc', updated_lock, decrypt=True)
            if digest(updated_lock) != manifest['effective_pnpm_lock_sha256']:
                raise ValueError('Updated sixth-product dependency lock checksum mismatch')
    shutil.copyfile(INPUTS / 'reference-package-lock.json', context / 'reference-package-lock.json')
    shutil.copyfile(INPUTS / 'reference-test-dependencies.txt', context / 'reference-test-dependencies.txt')
    shutil.copyfile(INPUTS / 'source.json', context / 'enhanced-provenance.json')
    dockerfile = (HERE / 'Dockerfile').read_text()
    dockerfile = dockerfile.replace('ghcr.io/astral-sh/uv:0.13.7 AS uv',
        'ghcr.io/astral-sh/uv:0.13.7@' + manifest['reference_uv_digest'] + ' AS uv')
    dockerfile = dockerfile.replace('FROM node:24.22.1-bookworm-slim',
        'FROM node:24.22.1-bookworm-slim@' + manifest['reference_node_digest'])
    install = next(line for line in dockerfile.splitlines() if line.startswith('RUN npm install --prefix /opt/products '))
    dockerfile = dockerfile.replace(install,
        'COPY reference-package-lock.json /opt/products/package-lock.json\n'
        'RUN node -e "const fs=require(\'fs\');const p=JSON.parse(fs.readFileSync(\'/opt/products/package-lock.json\'));fs.writeFileSync(\'/opt/products/package.json\',JSON.stringify(p.packages[\'\']))" '
        '&& npm ci --prefix /opt/products --no-audit --no-fund --dangerously-allow-all-scripts')
    dockerfile += '''
USER root
COPY reference-test-dependencies.txt /opt/reference-test-dependencies.txt
RUN diff -u /opt/reference-test-dependencies.txt /opt/test-dependencies.txt
COPY enhanced-source /opt/openclaw57
COPY enhanced-provenance.json /opt/openclaw57-provenance.json
RUN npm install --global --no-audit --no-fund pnpm@10.33.2
RUN cd /opt/openclaw57 && PUPPETEER_SKIP_DOWNLOAD=true pnpm install --frozen-lockfile
RUN cd /opt/openclaw57 && GIT_COMMIT=9c0e88e210b7bef3a2eb0ba9b0bed853077014a0 pnpm build:docker
RUN chmod -R a+rX /opt/openclaw57
USER 1000:1000
'''
    (context / 'Dockerfile').write_text(dockerfile)
    provenance = json.loads((output / 'preparation.json').read_text())
    provenance['enhanced_source'] = dict(manifest, actual_sdk_sha256=vendor_sha,
        source_tree_verified_before_vendor_addition=True,
        sdk_matches_original_lock=sdk_matches_lock,
        dependency_reproduction_only=diagnose_sdk,
        historical_reference_run=42959922129,
        historical_image_reusable=False,
        historical_image_limitation='Original image was runner-local and not retained; rebuild is not the same image. All six products use one new common image and three fresh repeats.',
        original_task_and_hidden_tests_unchanged=True)
    (output / 'preparation.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnose-sdk', action='store_true',
                        help='Prepare the exact mismatched delivery solely to reproduce the frozen build; do not run models')
    args = parser.parse_args()
    prepare(args.output.resolve(), diagnose_sdk=args.diagnose_sdk)
