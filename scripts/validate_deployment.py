"""Credential-free structural checks; not Databricks CLI/workspace validation."""
import argparse
import gzip
import json
import regex
from jsonschema import Draft202012Validator, validators, ValidationError
from copy import deepcopy
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def merge(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = deepcopy(base)
        for key, value in overlay.items():
            result[key] = merge(result[key], value) if key in result else deepcopy(value)
        return result
    if isinstance(base, list) and isinstance(overlay, list) and all(isinstance(v, dict) and 'name' in v for v in base+overlay):
        result = deepcopy(base)
        for value in overlay:
            index = next((i for i, existing in enumerate(result) if existing['name']==value['name']), None)
            if index is None: result.append(deepcopy(value))
            else: result[index] = merge(result[index], value)
        return result
    return deepcopy(overlay)


def load_bundle(target=None):
    bundle = yaml.safe_load((ROOT / 'databricks.yml').read_text())
    for name in bundle.get('include', []):
        bundle = merge(bundle, yaml.safe_load((ROOT / name).read_text()))
    return merge(bundle, bundle['targets'][target]) if target else bundle


def validate_schema(bundle):
    def pattern(validator, expression, instance, schema):
        if isinstance(instance, str) and not regex.search(expression, instance):
            yield ValidationError('Does not match pattern ' + expression)
    validator = validators.extend(Draft202012Validator, {'pattern':pattern})
    schema = json.loads(gzip.decompress((ROOT/'deployment/schema/databricks-cli.schema.json.gz').read_bytes()))
    errors = list(validator(schema).iter_errors(bundle))
    if errors:
        raise ValueError('Databricks bundle schema rejected configuration: ' + str(errors[0]))


def validate(target):
    bundle = load_bundle(target)
    validate_schema(bundle)
    apps = bundle['resources']['apps']
    expected = {'store_operations', 'storetime', 'opstask', 'confluence'} if target=='demo' else {'store_operations'}
    assert set(apps)==expected, 'Unexpected deployed App set'
    agent = apps['store_operations']
    env = {v['name']:v for v in agent['config']['env']}
    assert env['USER_AUTHORIZATION_MODE']['value']=='obo'
    assert env['UV_FROZEN']['value']=='true'
    assert env['UV_NO_DEFAULT_GROUPS']['value']=='true'
    assert 'DEMO_OPSTASK_WRITE_TOKEN' not in env or target=='demo'
    grants = {v['name']:v for v in agent['resources']}
    assert grants['opstask-read-mcp']['uc_securable']['securable_full_name'] != grants['opstask-write-mcp']['uc_securable']['securable_full_name']
    for name, app in apps.items():
        # Included files live under deployment/, so these paths resolve from there.
        source = (ROOT / 'deployment' / app['source_code_path']).resolve()
        assert source.is_relative_to(ROOT / '.deploy') and (source / '.layout-artifact.json').is_file(), f'Stage {name} first'
        for item in app['config'].get('env', []):
            if 'value_from' in item:
                assert item['value_from'] in {r['name'] for r in app['resources']}, 'Unbound App resource'
        assert '--no-default-groups' in app['config']['command']
        assert '--frozen' in app['config']['command']
        if name != 'store_operations':
            assert app['config']['command'][app['config']['command'].index('--package')+1]=='store-operations-demo-mcp'
    jobs = bundle['resources']['jobs']
    notebook = jobs['store_operations_background']['tasks'][0]['notebook_task']['notebook_path']
    assert (ROOT / 'deployment' / notebook).is_file()
    assert bundle['workspace']['host']=='${var.workspace_host}'
    return {'target':target, 'apps':sorted(apps), 'checks':'pinned Databricks CLI JSON schema, local structure and bindings', 'live_verified':False}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['dev','prod','demo'],default='dev')
    print(json.dumps(validate(parser.parse_args().target),indent=2))


if __name__=='__main__': main()
