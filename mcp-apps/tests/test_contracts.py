import asyncio,json
from pathlib import Path
import yaml
from scripts.export_demo_contracts import contracts

def test_published_contracts_and_separate_deployments():
    assert asyncio.run(contracts())==json.loads(Path('mcp-apps/contracts.json').read_text())
    from scripts.validate_deployment import load_bundle
    bundle=load_bundle('demo')
    assert set(bundle['resources']['apps'])=={'store_operations','storetime','opstask','confluence'}
    assert {'dev','prod','demo'} <= set(bundle['targets'])
    for cap in ['storetime','opstask','confluence']:
        app=bundle['resources']['apps'][cap]
        assert app['name']=='${var.'+cap+'_app_name}'
        assert app['config']['command']==['uv','run','--no-default-groups','demo-'+cap]
        assert app['source_code_path']=='../.deploy/'+cap
