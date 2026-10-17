"""Verbatim lexical retrieval only; never generates company policy."""
from pathlib import Path
import re
from shared.contracts import Document
from shared.demo_data import DATA, load_fixture
class Corpus:
    def __init__(self,index=None): self.index=Path(index or DATA/'policies/index.json')
    def documents(self):
        raw=load_fixture(self.index);base=self.index.parent.resolve();docs=[]
        for row in raw['documents']:
            metadata=dict(row);path=(base/metadata.pop('file')).resolve()
            if not path.is_relative_to(base): raise ValueError('Corpus path escapes fixture directory')
            document=Document(**metadata,text=path.read_text())
            if not document.source_url.startswith('https://demo.invalid/') or not document.text.strip(): raise ValueError('Invalid synthetic provenance')
            docs.append(document)
        if len({d.source_id for d in docs}) != len(docs): raise ValueError('Duplicate source ID')
        return sorted(docs,key=lambda d:d.source_id)
    def ready(self): self.documents()
    def get(self,source_id):
        for d in self.documents():
            if d.source_id==source_id: return d
        raise ValueError('Unknown synthetic document')
    def search(self,query,limit=5):
        if not query.strip() or not 1<=limit<=20: raise ValueError('Invalid search')
        tokens=set(re.findall(r'\w+',query.casefold()));ranked=[]
        for d in self.documents():
            score=len(tokens & set(re.findall(r'\w+',(d.title+' '+d.section+' '+d.text).casefold())))
            if score: ranked.append((score,d))
        return [d for _,d in sorted(ranked,key=lambda x:(-x[0],x[1].source_id))[:limit]]
