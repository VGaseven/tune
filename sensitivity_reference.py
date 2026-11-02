"""Read-only sensitivity capture from the selected source's sibling settings file."""
import hashlib
import re

KEYS={'EAresFloatSettingName::'+k for k in ('MouseSensitivity','MouseSensitivityADS','MouseSensitivityZoomed')}

def validate(reference):
    if not isinstance(reference,dict) or set(reference)!={'file_name','source_sha256','values'}:raise ValueError('Invalid sensitivity reference.')
    if reference['file_name']!='RiotUserSettings.ini' or not isinstance(reference['source_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',reference['source_sha256']):raise ValueError('Invalid sensitivity provenance.')
    values=reference['values']
    if not isinstance(values,dict) or not values or set(values)-KEYS:raise ValueError('Unsupported sensitivity keys.')
    for value in values.values():
        if not isinstance(value,str) or not re.fullmatch(r'\d{1,3}(\.\d{1,12})?',value) or not 0<=float(value)<=100:raise ValueError('Unsupported sensitivity value; no defaults substituted.')
    return reference

def parse(raw):
    if len(raw)>2_000_000:raise ValueError('Sensitivity file is too large.')
    encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
    section='';seen=False;values={}
    for line in raw.decode(encoding).splitlines():
        line=line.strip()
        if not line or line.startswith((';','#')):continue
        if line.startswith('[') and line.endswith(']'):
            section=line[1:-1]
            if section=='Settings':
                if seen:raise ValueError('Duplicate sensitivity settings section.')
                seen=True
        elif section=='Settings' and '=' in line:
            key,value=line.split('=',1);key=key.strip()
            if key in KEYS:
                if key in values:raise ValueError('Duplicate sensitivity setting.')
                values[key]=value.strip()
    if not values:return None
    return validate({'file_name':'RiotUserSettings.ini','source_sha256':hashlib.sha256(raw).hexdigest(),'values':values})

def read_sibling(source,reader):
    path=source.with_name('RiotUserSettings.ini')
    if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Linked sensitivity files are not supported.')
    if not path.exists():return None,None,None
    if not path.is_file():raise ValueError('Sensitivity source is not a regular file.')
    raw=reader(path)
    return parse(raw),path,raw
