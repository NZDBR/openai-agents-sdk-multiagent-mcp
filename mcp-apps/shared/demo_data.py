"""Only synthetic fixture access; future live adapters must be separate."""
import json
from pathlib import Path
DATA = Path(__file__).resolve().parent / 'data'
if not DATA.exists(): DATA = Path(__file__).resolve().parents[1] / 'data'
def load_fixture(path):
    data = json.loads(Path(path).read_text())
    if data.get('synthetic') is not True:
        raise ValueError('Demo fixture must be explicitly synthetic')
    return data
