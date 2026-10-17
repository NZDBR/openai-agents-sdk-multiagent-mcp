import pytest
from scripts.validate_demo_stack import DemoStack
@pytest.fixture(scope='module')
def demo_stack():
    with DemoStack() as stack: yield stack
