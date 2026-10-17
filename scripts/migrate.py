"""Apply the additive Lakebase schema using native rotating OAuth credentials."""
import os
import re
from pathlib import Path
from databricks_ai_bridge.lakebase import LakebaseClient


def main():
    from dotenv import load_dotenv
    load_dotenv()
    schema = os.getenv('STORE_OPS_SCHEMA', 'store_ops')
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', schema):
        raise ValueError('Invalid schema identifier')
    with LakebaseClient(autoscaling_endpoint=os.getenv('LAKEBASE_ENDPOINT') or os.environ['LAKEBASE_AUTOSCALING_ENDPOINT']) as client:
        for statement in Path('resources/schema.sql').read_text().split(';'):
            if statement.strip():
                client.execute(statement.replace('store_ops', schema))
    print('Store Operations schema migrated')

if __name__ == '__main__':
    main()
