"""Deployment structure/packaging checks, without workspace provisioning."""
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile
import pytest
from scripts.stage_apps import ROOT, MARKER, stage
from scripts.validate_deployment import load_bundle, validate


def test_only_demo_target_adds_mcp_apps():
    assert set(load_bundle('dev')['resources']['apps'])=={'store_operations'}
    assert set(load_bundle('prod')['resources']['apps'])=={'store_operations'}
    demo=load_bundle('demo')['resources']['apps']
    assert set(demo)=={'store_operations','storetime','opstask','confluence'}
    assert len({app['source_code_path'] for app in demo.values()})==4
    env={v['name']:v for v in demo['store_operations']['config']['env']}
    assert env['MCP_CONNECTION_MODE']['value']=='deployed_demo'
    assert env['DEMO_OPSTASK_READ_TOKEN']['value_from'] != env['DEMO_OPSTASK_WRITE_TOKEN']['value_from']
    assert not (ROOT/'mcp-apps/databricks.yml').exists()
    assert not (ROOT/'e2e-chatbot-app-next/databricks.yml').exists()


@pytest.mark.parametrize('component',['agent','storetime'])
def test_artifact_exclusions_and_frozen_lock_versions(tmp_path,component):
    output=stage(component,tmp_path)
    manifest=json.loads((output/MARKER).read_text())
    paths=set(manifest['files'])
    assert not any(p.startswith(('tests/','docs/','.github/','omnigent/')) for p in paths)
    assert not any(Path(p).name.startswith('.env') for p in paths)
    assert not any('node_modules' in p or '/tests/' in p for p in paths)
    assert not (output/'scripts/stage_apps.py').exists()
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest()==digest
    assert (output/'uv.lock').read_bytes()==(ROOT/'uv.lock').read_bytes()
    assert (output/'mcp-apps/pyproject.toml').read_bytes()==(ROOT/'mcp-apps/pyproject.toml').read_bytes()
    requirements=(output/'requirements.txt').read_text()
    assert '-e ' not in requirements and 'store-operations-demo-mcp==' not in requirements
    assert 'pytest==' not in requirements
    assert (output/'requirements.txt').is_file()
    if component=='agent':
        assert sorted(p.relative_to(output/'mcp-apps').as_posix() for p in (output/'mcp-apps').rglob('*'))==['pyproject.toml']
        assert (output/'e2e-chatbot-app-next/packages/db/src/queries.ts').is_file()
        assert (output/'e2e-chatbot-app-next/scripts/migrate.ts').is_file()
        assert (output/'scripts/start_app.py').read_bytes()==(ROOT/'scripts/start_app.py').read_bytes()
        assert manifest['package']=='store-operations-agent'
    else:
        assert not (output/'agent_server').exists()
        assert not (output/'e2e-chatbot-app-next').exists()
        assert (output/'mcp-apps/data/policies/protected-training.md').is_file()
        assert manifest['package']=='store-operations-demo-mcp'


def test_stager_will_not_delete_unowned_files(tmp_path):
    directory=tmp_path/'agent';directory.mkdir()
    (directory/'important.txt').write_text('keep')
    with pytest.raises(ValueError,match='unowned'): stage('agent',tmp_path)
    assert (directory/'important.txt').read_text()=='keep'


def test_production_and_demo_wheels_are_separate(tmp_path):
    subprocess.run(['uv','build','--all-packages','--wheel','--out-dir',str(tmp_path)],cwd=ROOT,check=True,capture_output=True)
    core=next(tmp_path.glob('store_operations_agent-*.whl'))
    demo=next(tmp_path.glob('store_operations_demo_mcp-*.whl'))
    with ZipFile(core) as wheel:
        names=wheel.namelist()
        assert 'agent_server/identity.py' in names
        assert 'evaluations/datasets/store_operations.jsonl' in names
        assert not any(p.startswith(('storetime/','opstask/','confluence/','shared/data/')) for p in names)
    with ZipFile(demo) as wheel:
        names=wheel.namelist()
        assert 'storetime/server.py' in names and 'shared/data/storetime.json' in names
        assert not any(p.startswith('agent_server/') for p in names)


def test_pinned_official_schema_rejects_inline_app_yaml_spelling():
    from scripts.validate_deployment import validate_schema
    bundle=load_bundle('demo')
    validate_schema(bundle)
    binding=next(v for v in bundle['resources']['apps']['storetime']['config']['env'] if 'value_from' in v)
    binding['valueFrom']=binding.pop('value_from')
    with pytest.raises(ValueError,match='schema rejected'):
        validate_schema(bundle)


@pytest.mark.parametrize('component',['agent','storetime'])
def test_staging_is_offline_cache_independent_and_never_resolves(tmp_path,monkeypatch,component):
    import scripts.stage_apps as stager
    cache=tmp_path/'empty-uv-cache'
    monkeypatch.setenv('UV_CACHE_DIR',str(cache))
    monkeypatch.setenv('UV_OFFLINE','true')
    monkeypatch.setenv('UV_PYTHON_DOWNLOADS','never')
    actual_run=stager.subprocess.run
    exports=[]
    def guarded_run(command,**kwargs):
        assert command[:2] != ['uv','lock'], 'Staging must not run a new resolver'
        if command[:2]==['uv','export']:
            exports.append(command)
            assert '--frozen' in command and '--offline' in command
        return actual_run(command,**kwargs)
    monkeypatch.setattr(stager.subprocess,'run',guarded_run)
    artifact=stage(component,tmp_path/'artifacts')
    assert len(exports)==1
    assert (artifact/'uv.lock').read_bytes()==(ROOT/'uv.lock').read_bytes()
    assert (artifact/'requirements.txt').is_file()


def test_export_failure_surfaces_stderr_and_preserves_previous_artifact(tmp_path,monkeypatch):
    import scripts.stage_apps as stager
    directory=tmp_path/'agent';directory.mkdir()
    (directory/MARKER).write_text('{}')
    (directory/'preserved.txt').write_text('previous successful artifact')
    actual_run=stager.subprocess.run
    def fail_export(command,**kwargs):
        if command[:2]==['uv','export']:
            raise subprocess.CalledProcessError(1,command,stderr='test-only useful export diagnostic')
        return actual_run(command,**kwargs)
    monkeypatch.setattr(stager.subprocess,'run',fail_export)
    with pytest.raises(RuntimeError,match='useful export diagnostic'):
        stage('agent',tmp_path)
    assert (directory/'preserved.txt').read_text()=='previous successful artifact'


@pytest.mark.parametrize('component,package,module',['agent store-operations-agent agent_server.identity'.split(),
                                                    'storetime store-operations-demo-mcp storetime.server'.split()])
def test_frozen_artifact_installs_only_selected_runtime(tmp_path,component,package,module):
    artifact=stage(component,tmp_path)
    result=subprocess.run(['uv','sync','--frozen','--offline','--no-default-groups','--package',package],
                          cwd=artifact,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    absent='storetime' if component=='agent' else 'agent_server'
    check=f'''import importlib, importlib.util
from pathlib import Path
module=importlib.import_module({module!r})
assert Path(module.__file__).is_relative_to(Path.cwd()), module.__file__
assert importlib.util.find_spec({absent!r}) is None
'''
    subprocess.run([str(artifact/'.venv/bin/python'),'-c',check],cwd=artifact,check=True,capture_output=True,text=True)
    assert (artifact/'uv.lock').read_bytes()==(ROOT/'uv.lock').read_bytes()
