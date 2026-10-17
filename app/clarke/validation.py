import re
import unicodedata
from datetime import date, datetime
from zoneinfo import ZoneInfo
import phonenumbers
from .core import fail, now, LOCATIONS

NY=ZoneInfo('America/New_York')
ITEMS={'shoes','boots','handbag_purse','belt_strap','leather_garment','luggage','baseball_glove','other_leather','keys'}
WORK={'soles_heels','heel_tips','stretch_fit','orthopedic_modification','stitching','zipper','dye_color','clean_condition','straps_hardware','not_sure'}

def text(value,field,low=1,high=2000,optional=False):
    if optional and (value is None or value==''):return None
    if not isinstance(value,str):fail(field)
    value=unicodedata.normalize('NFC',value.strip())
    if not low<=len(value)<=high or any(unicodedata.category(ch)=='Cc' and ch not in '\n\t' for ch in value) or '<' in value or '>' in value:
        fail(field,f'Use plain text, {low}–{high} characters.')
    return value

def enum(value,values,field):
    if not isinstance(value,str) or value not in values:fail(field,'Choose an available option.')
    return value

def integer(value,field,low,high):
    if type(value) is not int or not low<=value<=high:fail(field,f'Use a whole number from {low} to {high}.')
    return value

def boolean(value,field):
    if type(value) is not bool:fail(field)
    return value

def email(value,field='email',optional=False):
    if optional and not value:return None
    value=text(value,field,1,254).casefold()
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",value) or '..' in value or value.startswith('.') or '.@' in value:
        fail(field,'Enter one valid email address.')
    return value

def phone(value,field='phone',optional=False):
    if optional and not value:return None
    value=text(value,field,1,40)
    if not re.fullmatch(r'\+?[0-9() .-]+',value):fail(field,'Enter a valid phone number without an extension.')
    try:
        number=phonenumbers.parse(value,'US')
        if not phonenumbers.is_valid_number(number) or number.extension:raise ValueError()
        if not value.startswith('+') and number.country_code!=1:raise ValueError()
        return phonenumbers.format_number(number,phonenumbers.PhoneNumberFormat.E164)
    except (ValueError,phonenumbers.NumberParseException):fail(field,'Enter a valid phone number, including country code outside the US.')

def unique_array(value,field,allowed,maximum,minimum=0):
    if not isinstance(value,list) or not minimum<=len(value)<=maximum or any(not isinstance(x,str) for x in value) or len(set(value))!=len(value) or (allowed is not None and not set(value)<=allowed):fail(field)
    return value

def contact(value,online):
    if not isinstance(value,dict) or set(value)-{'name','email','phone','preferred'}:fail('contact')
    result={'name':text(value.get('name'),'contact.name',1,100),'email':email(value.get('email'),'contact.email',not online),'phone':phone(value.get('phone'),'contact.phone',True),'preferred':enum(value.get('preferred'),{'email','call','text'},'contact.preferred')}
    if not (result['email'] or result['phone']):fail('contact.email','Provide an email or phone number.')
    if result['preferred']=='email' and not result['email']:fail('contact.email','Email is required for this contact preference.')
    if result['preferred'] in ('call','text') and not result['phone']:fail('contact.phone','A phone number is required for calls or texts.')
    return result

def repair(p,online=True):
    work=unique_array(p.get('workTypes',[]),'workTypes',WORK,10)
    if 'not_sure' in work and len(work)>1:fail('workTypes','Choose not sure by itself.')
    needed=p.get('neededBy') or None
    if needed is not None:
        try:
            day=date.fromisoformat(needed)
            if day.isoformat()!=needed or day<datetime.fromtimestamp(now()/1000,NY).date():raise ValueError()
        except (ValueError,TypeError):fail('neededBy','Choose today or a later date.')
    return {'itemType':enum(p.get('itemType'),ITEMS,'itemType'),'workTypes':sorted(work),'description':text(p.get('description'),'description',10,2000),'brandAge':text(p.get('brandAge'),'brandAge',1,120,True),'neededBy':needed,'location':enum(p.get('location'),LOCATIONS,'location'),'contact':contact(p.get('contact'),online)}

def reference(value):
    if not isinstance(value,str):return ''
    compact=value.upper().replace('-','').replace(' ','')
    if compact.startswith('CLK'):compact=compact[3:]
    compact=compact.translate(str.maketrans({'O':'0','I':'1','L':'1'}))
    return compact if re.fullmatch('[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{26}',compact) else ''
