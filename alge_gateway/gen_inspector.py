"""Read-only structural inspection of supplied SwimTime 2.4.10.1 samples.

No field is adopted as rank, lane, official time, backup time, round or status.
The Generic field specification and paired official report are still required.
"""
import hashlib,re
from results_backend.store import DomainError

def inspect_text(text,filename='upload.gen'):
    if not isinstance(text,str) or not text or len(text.encode('utf-8'))>200000:
        raise DomainError('GEN text must contain 1..200000 UTF-8 bytes')
    if not isinstance(filename,str) or not re.fullmatch(r'[A-Za-z0-9_. -]{1,100}\.gen',filename,re.I):
        raise DomainError('Use a plain .gen filename without directories')
    if '\x00' in text:raise DomainError('Binary GEN input rejected')
    lines=text.splitlines()
    if len(lines)>100:raise DomainError('GEN sample exceeds 100 lines')
    header=lines[0].split(';')
    if len(header)!=7 or header[5]!='Alge-Timing' or header[6]!='2.4.10.1':
        raise DomainError('Unsupported GEN header; only the supplied ALGE 2.4.10.1 sample profile is recognised')
    rows=[];count=0
    for number,line in enumerate(lines[1:],1):
        fields=line.split(';')
        if len(fields)!=6:raise DomainError('Expected six raw fields on row '+str(number))
        numeric=[]
        for index,value in enumerate(fields):
            if re.fullmatch(r'(?:\d+:)*\d+\.\d{2}',value):numeric.append({'field_index_zero_based':index,'raw_value':value})
        count+=bool(numeric)
        rows.append({'row_index_one_based':number,'raw_fields':fields,'time_like_values':numeric,'semantics':'UNRESOLVED'})
    return {'filename':filename,'profile':'alge-gen-2.4.10.1-structural-review-v1','sha256':hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'header_fields':header,'rows':rows,'rows_with_time_like_values':count,'adopted_as_results':False,
            'status':'INSPECTED / FIELD MAPPING NOT VERIFIED','live_clock_supported':False,
            'warnings':['No athlete identity in these samples','Row order is not asserted to be lane order','P, Q, header values and time-like columns remain unresolved','File sequence is not assumed to mean correction precedence','No OFFICIAL result is created by this inspector']}
