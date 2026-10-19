"""Deployment structure/packaging checks, without workspace provisioning."""
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
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
    lock=tomllib.loads((output/'uv.lock').read_text())
    canonical=tomllib.loads((ROOT/'uv.lock').read_text())
    assert {(p['name'],p['version']) for p in lock['package']} <= {(p['name'],p['version']) for p in canonical['package']}
    assert (output/'requirements.txt').is_file()
    if component=='agent':
        assert not (output/'mcp-apps').exists()
        assert (output/'e2e-chatbot-app-next/packages/db/src/queries.ts').is_file()
        assert (output/'e2e-chatbot-app-next/scripts/migrate.ts').is_file()
        assert (output/'scripts/start_app.py').read_bytes()==(ROOT/'scripts/start_app.py').read_bytes()
        assert not any(p['name']=='store-operations-demo-mcp' for p in lock['package'])
    else:
        assert not (output/'agent_server').exists()
        assert not (output/'e2e-chatbot-app-next').exists()
        assert (output/'mcp-apps/data/policies/protected-training.md').is_file()
        assert not any(p['name']=='store-operations-agent' for p in lock['package'])


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
