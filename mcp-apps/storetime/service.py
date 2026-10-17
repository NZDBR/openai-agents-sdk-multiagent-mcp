"""Read-only deterministic training records; no corporate connection."""
from datetime import date
from shared.contracts import Schedule, TrainingBlock, CoverageReason, TrainingHours, Diagnostic
from shared.demo_data import DATA, load_fixture
class StoreTime:
    def __init__(self,path=None): self.path=path or DATA/'storetime.json'
    def load(self):
        raw=load_fixture(self.path)
        schedules=[Schedule.model_validate(x) for x in raw['schedules']]
        blocks=[TrainingBlock.model_validate(x) for x in raw['blocks']]
        reasons=[CoverageReason.model_validate(x) for x in raw['reasons']]
        for rows,key in [(schedules,'schedule_id'),(blocks,'block_id'),(reasons,'reason_id')]:
            if len({getattr(x,key) for x in rows}) != len(rows): raise ValueError('Duplicate fixture ID')
        ids={b.block_id for b in blocks}
        for b in blocks:
            if b.completed_hours+b.converted_hours>b.scheduled_hours: raise ValueError('Inconsistent training hours')
        if any(x.store_id not in raw['stores'] for x in schedules+blocks) or any(x.block_id not in ids for x in reasons):
            raise ValueError('Unknown fixture reference')
        return raw['stores'],schedules,blocks,reasons
    def ready(self): self.load()
    def window(self,store_id,start_date,end_date):
        start_date,end_date=date.fromisoformat(str(start_date)),date.fromisoformat(str(end_date))
        if start_date>end_date: raise ValueError('Reversed date window')
        stores,schedules,blocks,reasons=self.load()
        if store_id not in stores: raise ValueError('Unknown synthetic store')
        schedules=[s for s in schedules if s.store_id==store_id and start_date<=s.date<=end_date]
        blocks=[b for b in blocks if b.store_id==store_id and start_date<=b.date<=end_date]
        return schedules,blocks,[r for r in reasons if r.block_id in {b.block_id for b in blocks}]
    def hours(self,store_id,start_date,end_date):
        _,blocks,_=self.window(store_id,start_date,end_date)
        return TrainingHours(store_id=store_id,start_date=start_date,end_date=end_date,
          scheduled_hours=sum(b.scheduled_hours for b in blocks),protected_hours=sum(b.scheduled_hours for b in blocks if b.protected),
          completed_hours=sum(b.completed_hours for b in blocks),converted_hours=sum(b.converted_hours for b in blocks))
    def diagnose(self,store_id,start_date,end_date):
        _,blocks,reasons=self.window(store_id,start_date,end_date)
        hours=self.hours(store_id,start_date,end_date)
        return Diagnostic(hours=hours,completion_gap_hours=hours.scheduled_hours-hours.completed_hours,coverage_reasons=reasons,
          evidence_block_ids=[b.block_id for b in blocks],limitations=['Synthetic demo records, not live employee data.','Recorded reasons are contributors, not proof of every incomplete hour.'])
