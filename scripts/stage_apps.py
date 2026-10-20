"""Assemble explicit, secret-free source-build App artifacts without runtime edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.layout-artifact.json'
DEMO_SERVICES = ('storetime', 'opstask', 'confluence')


def files_for(component):
    metadata = {'pyproject.toml', 'uv.lock', 'mcp-apps/pyproject.toml', 'README.md', 'LICENSE', 'NOTICE'}
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = set(metadata)
    for name in filter(None, tracked):
        path = Path(name)
        if component == 'agent':
            if path.parts[0] in {'agent_server', 'evaluations', 'jobs'}:
                selected.add(name)
            if name in {'scripts/__init__.py', 'scripts/start_app.py', 'scripts/app_diagnostics.py'}:
                selected.add(name)
            if path.parts[0] == 'e2e-chatbot-app-next':
                relative = path.parts[1:]
                if relative[0] in {'client', 'server', 'packages'} or '/'.join(relative) in {
                    'package.json', 'package-lock.json', 'tsconfig.json', 'scripts/migrate.ts'}:
                    if not any(p in {'tests', 'node_modules', 'dist', '__pycache__'} for p in relative) and not path.name.startswith('.env') and path.suffix not in {'.md', '.yaml', '.yml'}:
                        selected.add(name)
        elif len(path.parts) >= 3 and path.parts[0] == 'mcp-apps' and path.parts[1] in {'shared', *DEMO_SERVICES, 'data'}:
            if path.suffix in {'.py', '.json', '.md'}:
                selected.add(name)
    return sorted(selected)


def stage(component, output_root=None):
    if component not in ('agent', *DEMO_SERVICES):
        raise ValueError('Unknown App component')
    output_root = Path(output_root or ROOT / '.deploy')
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / component
    if destination.is_symlink() or (destination.exists() and not (destination / MARKER).is_file()):
        raise ValueError('Refusing to replace an unowned artifact directory')
    with tempfile.TemporaryDirectory(dir=output_root, prefix='.staging-') as temporary:
        temporary = Path(temporary)
        for name in files_for(component):
            source = ROOT / name
            if source.is_symlink() or not source.is_file():
                raise ValueError('Missing or symlinked source: ' + name)
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        # Developer console utilities are deliberately absent from runtime artifacts.
        metadata = temporary / 'pyproject.toml'
        text = metadata.read_text()
        # Retain both workspace manifests and their original package locations.
        # The agent carries only demo metadata, never demo server code or data.
        # Disabling default groups avoids installing development tools in children
        # started by the existing, unchanged start-app launcher.
        text = text.replace('default-groups = ["dev", "setup"]', 'default-groups = []')
        for command, module in [('quickstart','quickstart'), ('discover-tools','discover_tools'), ('preflight','preflight')]:
            text = text.replace(f'{command} = "scripts.{module}:main"\n', '')
        metadata.write_text(text)
        # Consume the canonical lock verbatim. Re-locking these filtered source
        # trees would require a fresh universal resolution (including platforms
        # not cached by the preceding uv sync). Export needs no registry/cache.
        package = 'store-operations-agent' if component == 'agent' else 'store-operations-demo-mcp'
        command = ['uv', 'export', '--frozen', '--offline', '--package', package,
                   '--no-default-groups', '--no-hashes', '--no-emit-workspace',
                   '--directory', str(temporary), '-o', str(temporary/'requirements.txt')]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f'Cannot export {component} requirements from the canonical lock:\n{error.stderr}') from error
        if (temporary/'uv.lock').read_bytes() != (ROOT/'uv.lock').read_bytes():
            raise ValueError('Artifact export modified the canonical workspace lock')
        hashes = {str(p.relative_to(temporary)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(temporary.rglob('*')) if p.is_file()}
        (temporary / MARKER).write_text(json.dumps({'component':component, 'package':package, 'files':hashes}, indent=2)+'\n')
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(temporary), destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['dev', 'prod', 'demo'], default='dev')
    args = parser.parse_args()
    components = ('agent', *DEMO_SERVICES) if args.target == 'demo' else ('agent',)
    for component in components:
        artifact = stage(component)
        print(f'{component}: {artifact}')


if __name__ == '__main__':
    main()
