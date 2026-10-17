import asyncio,json
from pathlib import Path
import yaml
from scripts.export_demo_contracts import contracts

def test_published_contracts_and_separate_deployments():
    assert asyncio.run(contracts())==json.loads(Path('mcp-apps/contracts.json').read_text())
    bundle=yaml.safe_load(Path('mcp-apps/databricks.yml').read_text())
    assert set(bundle['resources']['apps'])=={'storetime','opstask','confluence'}
    assert set(bundle['targets'])=={'dev','prod'}
    for cap,app in bundle['resources']['apps'].items():
        assert app['name']=='${var.'+cap+'_app_name}'
        assert app['config']['command']==['uv','run','demo-'+cap]
        assert yaml.safe_load(Path(f'mcp-apps/{cap}/app.yaml').read_text())==app['config']
