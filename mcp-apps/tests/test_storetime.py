from datetime import date
import pytest
from storetime.service import StoreTime

def test_training_diagnostics_and_window():
    service=StoreTime();args=('DEMO-001',date(2026,1,5),date(2026,1,6))
    schedules,blocks,reasons=service.window(*args)
    assert len(schedules)==len(blocks)==len(reasons)==2
    result=service.diagnose(*args)
    assert result.hours.scheduled_hours==6 and result.hours.completed_hours==3
    assert result.hours.protected_hours==6 and result.hours.converted_hours==2
    assert result.completion_gap_hours==3 and result.evidence_block_ids==['B-1','B-2']
    assert service.hours('DEMO-002',*args[1:]).scheduled_hours==0
    assert len(service.window('DEMO-001',date(2026,1,5),date(2026,1,5))[1])==1
    with pytest.raises(ValueError): service.window('UNKNOWN',*args[1:])
    with pytest.raises(ValueError): service.window('DEMO-001',date(2026,1,6),date(2026,1,5))
