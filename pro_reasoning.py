"""Bounded live research and context rules; no user-code execution or direct URL fetches."""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
import requests

SCOPES = ('web', 'social', 'facebook', 'tiktok')
TIMEZONE = ZoneInfo('Africa/Tripoli')
CONTEXT_RULES = '''
افهم اللهجة الليبية والأخطاء الإملائية والاختصار من سياق المحادثة: نبي=أريد، توا=الآن، دير=نفّذ، حول/حاول=حاول بحسب السياق.
«عدلها/نفسه/كمّل/زيده/الأول/الثاني» تشير لأقرب موضوع مناسب واضح، وليس بالضرورة آخر كلمة. التصحيح الأحدث يلغي القديم.
إذا كان المرجع واضحاً نفذ مباشرة، وإذا اختلفت نتيجتان مادياً اسأل سؤالاً واحداً محدداً؛ لا تخترع نية أو اسماً أو رقماً.
الملف الحالي هو مصدر التعديل. إذا غاب الأصل فلا تدعِ تعديله؛ وضّح الحاجة لإرفاقه أو زر متابعة تعديله.
حلل الطلب على مراحل داخلياً: الهدف، القيود، الأدوات، مراجعة النتيجة. لا تعرض تفكيرك الداخلي للمستخدم.
أخبار المنتجات والأسعار والمواصفات والتوفر والتوصيات والقوانين والصحة والتوثيق البرمجي المتغير تحتاج بحثاً حديثاً.
لا تستنتج عدم وجود موديل من غيابه عن معرفتك أو من نتائج قليلة. ابحث في موقع الشركة واذكر حدود التحقق.
وسّع البحث عندما تختلف المصادر، وفضّل الوثائق الرسمية على ملخصات المدونات. لا تخلط تاريخ المقال بتاريخ الحدث.
افصل ما تثبته المصادر عن استنتاجك. لا تدعِ مشاهدة صورة أو قراءة صفحة كاملة إذا المتاح مجرد مقتطف.
للمرفقات: انسخ الأسماء والأصفار والمقاسات كما هي؛ راجع الحسابات، ولا تعالج الفرق بتغيير قراءة الأصل.
قبل الرد راجع أنه يجيب عن طلب المستخدم ويحترم قيوده وأن أي «تم» يستند لأداة ناجحة.
'''

def normalize(text):
    value=unicodedata.normalize('NFKC',str(text or '')).lower()
    value=''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',value.translate(str.maketrans('أإآىة','ااايه'))).strip()

def history_for_search(rows):
    """Remove only known attachment metadata; preserve user text and bracketed lines."""
    cleaned=[]
    for row in rows:
        message=str(row.get('message',''))
        lines=[line for line in message.splitlines() if line.strip()!='[PRO_EXTERNAL_CONTEXT_V1]'
               and not re.fullmatch(r'\[مرفق ملف: [^\n]*\]|\[مرفق: (?:صورة|ثلاث لقطات فيديو بدون صوت)\]',line.strip())]
        cleaned.append({'role':row.get('role','user'),'message':'\n'.join(lines)})
    return cleaned


def wants_images(message):
    return bool(re.search(r'صور|صوره|وريني|بالصور|images?|photos?',normalize(message)))

def search_intent(message, force=False, scope=None, rows=None, attached=False):
    text=normalize(message)
    explicit=bool(re.search(r'ابحث|ابحت|دور\s*لي|دو.?رلي|فتش|تاكد|تحقق|search|look up',text))
    if not force and not explicit and re.search(r'(صمم|صم.?م|بني|انشئ|دير|عدل).{0,15}(صوره|تصميم)',text):return None
    facebook=bool(re.search(r'فيس|facebook',text));tiktok=bool(re.search(r'تيك|تك توك|tiktok|tik tok',text))
    social=facebook or tiktok
    # Local edits and OCR never need external lookup unless explicitly requested.
    if not force and not explicit and (attached or re.search(r'(في|داخل|من)\s+(الملف|المستند|الجدول|الفاتوره|الصوره|الذاكره)',text)):
        return None
    topical=bool(re.search(r'سعر|اسعار|متوفر|توصي|تنصح|رشح|اختار.*(هاتف|جهاز|عطر)|اخر اصدار|احدث|مواصفات|يدعم|نزل|اعلن|اخبار|قانون|دواء|جرعه|علاج|تفعيل|برمج|api|firmware|samsung|galaxy|iphone|redmagic|realme|infinix|huawei|سامسونج|جالكسي|ايفون|هواوي|ريدماجيك|ريلمي|انفنكس',text))
    page=bool(re.search(r'(عط|هات|نبي|جيب|وريني).{0,35}(صفحه|رابط|حساب|موقع)',text))
    followup=bool(re.fullmatch(r'(و?)(سعره|بكم|قداش|يدعمها|متوفر|والثاني|شنو الافضل|ايهم افضل)[؟? ]*',text))
    if not (force or explicit or topical or social or page or followup):return None
    selected=scope if force and scope in SCOPES else 'web'
    if social:selected='social' if facebook and tiktok else 'facebook' if facebook else 'tiktok'
    if page and 'صفحه' in text and not tiktok:selected='facebook'
    query=message.strip()[:500]
    if followup and rows:
        rows=history_for_search(rows)
        context=[str(r.get('message',''))[:450] for r in rows[-5:] if r.get('message')!=message]
        if context:query=(' '.join(context[-2:])+' '+message)[-900:]
    return {'query':query,'scope':selected,'include_images':wants_images(message),'original_message':message[:500]}

def safe_url(value):
    if not isinstance(value,str) or len(value)>2048:return False
    try:
        p=urlsplit(value);host=(p.hostname or '').lower()
        if p.scheme not in ('http','https') or not host or p.username or p.password:return False
        if host=='localhost' or host.endswith(('.local','.internal')):return False
        import ipaddress
        try:return ipaddress.ip_address(host).is_global
        except ValueError:return '.' in host
    except ValueError:return False

def research(spec, serper_key='', tavily_key='', post=None):
    """At most three queries, provider fallback, deduplication and optional extraction."""
    post=post or requests.post
    scope=spec.get('scope','web');query=str(spec.get('query','')).strip()[:500]
    if scope not in SCOPES or not query:raise ValueError('موضوع البحث أو نطاقه غير صالح.')
    stamp=datetime.now(TIMEZONE).isoformat(timespec='minutes')
    result={'query':query,'scope':scope,'searched_at':stamp,'results':[],'images':[],'warnings':[]}
    if not (serper_key or tavily_key):
        result['warnings']=['البحث غير مفعّل؛ يلزم SERPER_API_KEY أو TAVILY_API_KEY في إعدادات الاستضافة. لم يتم التحقق من المعلومة الحالية.']
        result['status']='unavailable';return result
    variants=[query]
    for q in spec.get('queries',[]) if isinstance(spec.get('queries'),list) else []:
        if isinstance(q,str) and 2<=len(q.strip())<=500 and normalize(q) not in {normalize(v) for v in variants}:variants.append(q.strip())
    if scope=='web' and len(variants)==1:
        variants.append(query+' official '+str(datetime.now(TIMEZONE).year))
    domains={'web':[None],'social':['facebook.com','tiktok.com'],'facebook':['facebook.com'],'tiktok':['tiktok.com']}[scope]
    jobs=[(q,d) for q in variants[:3 if scope=='web' else 1] for d in domains]
    def fetch(job):
        q,domain=job;errors=[]
        providers=([('serper',serper_key)] if serper_key else [])+([('tavily',tavily_key)] if tavily_key else [])
        for provider,key in providers:
            try:
                if provider=='serper':
                    response=post('https://google.serper.dev/search',headers={'X-API-KEY':key},json={'q':q+(' site:'+domain if domain else ''),'num':8,'hl':'ar'},timeout=(5,16))
                else:
                    payload={'query':q,'search_depth':'advanced','max_results':6,'include_answer':False,'include_raw_content':True,'include_images':spec.get('include_images') is True}
                    if domain:payload['include_domains']=[domain]
                    response=post('https://api.tavily.com/search',headers={'Authorization':'Bearer '+key},json=payload,timeout=(5,16))
                if response.status_code!=200:
                    errors.append(provider+': '+('حد الاستخدام أو الرصيد' if response.status_code in (429,432,433) else 'تعذر الاتصال أو التحقق من المفتاح'));continue
                data=response.json()
                if not isinstance(data,dict):raise ValueError('invalid provider response')
                entries=data.get('organic',[]) if provider=='serper' else data.get('results',[])
                if not isinstance(entries,list):raise ValueError('invalid result list')
                found=[]
                for item in entries[:8]:
                    if not isinstance(item,dict):continue
                    url=item.get('link') if provider=='serper' else item.get('url')
                    if not safe_url(url):continue
                    host=urlsplit(url).hostname.lower()
                    if domain and host!=domain and not host.endswith('.'+domain):continue
                    if domain:
                        haystack=normalize(str(item.get('title') or '')+' '+str(item.get('content') or item.get('snippet') or ''))
                        anchors=spec.get('required_terms',[])
                        if isinstance(anchors,list) and any(normalize(t) not in haystack for t in anchors if isinstance(t,str) and normalize(t)):continue
                    raw=item.get('raw_content') if provider=='tavily' else None
                    found.append({'title':str(item.get('title') or host)[:250],'url':url,'content':str(raw or item.get('content') or item.get('snippet') or '')[:4000 if raw else 1600],'content_kind':'page_extract' if raw else 'search_snippet','published_date':str(item.get('published_date') or item.get('date') or '')[:80],'platform':host,'provider':provider})
                images=[]
                if spec.get('include_images'):
                    image_data=data.get('images',[]) if provider=='tavily' else []
                    if provider=='serper':
                        try:
                            im=post('https://google.serper.dev/images',headers={'X-API-KEY':key},json={'q':q+(' site:'+domain if domain else ''),'num':6},timeout=(5,10))
                            if im.status_code==200:image_data=im.json().get('images',[])
                        except (requests.RequestException,ValueError,AttributeError):errors.append('تعذر جلب الصور.')
                    for item in image_data[:6] if isinstance(image_data,list) else []:
                        if isinstance(item,str):item={'url':item}
                        if not isinstance(item,dict):continue
                        url=item.get('url') or item.get('imageUrl');source=item.get('source_url') or item.get('link')
                        if not safe_url(url) or not url.startswith('https://'):continue
                        if domain and (not safe_url(source) or not (urlsplit(source).hostname==domain or urlsplit(source).hostname.endswith('.'+domain))):continue
                        preview=item.get('thumbnailUrl') or item.get('preview_url')
                        images.append({'url':url,'source_url':source if safe_url(source) else None,'preview_url':preview if safe_url(preview) else None,'description':str(item.get('description') or item.get('title') or '')[:350],'platform':domain or urlsplit(url).hostname})
                if found:return found,images,errors
                errors.append(provider+': لم تظهر نتائج مطابقة؛ هذا لا يثبت عدم وجود المطلوب.')
            except (requests.RequestException,ValueError,TypeError,AttributeError):errors.append(provider+': تعذرت محاولة البحث.')
        return [],[],errors
    with ThreadPoolExecutor(max_workers=3) as pool:batches=list(pool.map(fetch,jobs))
    seen=set();seen_images=set()
    for entries,images,warnings in batches:
        result['warnings'].extend(warnings)
        for item in entries:
            canonical=item['url'].split('#')[0].rstrip('/')
            if canonical not in seen:seen.add(canonical);result['results'].append(item)
        for item in images:
            if item['url'] not in seen_images:seen_images.add(item['url']);result['images'].append(item)
    # Prefer known first-party domains for named manufacturers and software services.
    primary={'samsung':('samsung.com',),'سامسونج':('samsung.com',),'galaxy':('samsung.com',),
             'apple':('apple.com',),'iphone':('apple.com',),'ايفون':('apple.com',),
             'huawei':('huawei.com',),'هواوي':('huawei.com',),'realme':('realme.com',),
             'infinix':('infinixmobility.com',),'redmagic':('redmagic.gg',),
             'openai':('openai.com',),'groq':('groq.com',),'render':('render.com',),
             'tavily':('tavily.com',),'python':('python.org',)}
    preferred=tuple(d for term,hosts in primary.items() if term in normalize(query) for d in hosts)
    if scope=='web' and preferred:
        result['results'].sort(key=lambda r:0 if any(r['platform']==d or r['platform'].endswith('.'+d) for d in preferred) else 1)
    result['results']=result['results'][:10];result['images']=result['images'][:6]
    for index,row in enumerate(result['results'],1):row['id']=index
    # Extraction runs at the fixed provider endpoint, never requests user-supplied hosts directly.
    if tavily_key:
        urls=[r['url'] for r in result['results'] if r['content_kind']=='search_snippet'][:3]
        if urls:
            try:
                response=post('https://api.tavily.com/extract',headers={'Authorization':'Bearer '+tavily_key},json={'urls':urls,'extract_depth':'basic','format':'text'},timeout=(5,12))
                if response.status_code!=200:raise ValueError('extract failed')
                extracted=response.json().get('results',[])
                for item in extracted if isinstance(extracted,list) else []:
                    if not isinstance(item,dict) or item.get('url') not in urls or not isinstance(item.get('raw_content'),str):continue
                    for row in result['results']:
                        if row['url']==item['url'] and item['raw_content'].strip():row.update(content=item['raw_content'][:4000],content_kind='page_extract')
            except (requests.RequestException,ValueError,AttributeError):result['warnings'].append('تعذر استخراج نص الصفحات؛ بعض الأدلة مقتطفات بحث فقط.')
    if any(r['content_kind']=='search_snippet' for r in result['results']):result['warnings'].append('بعض المصادر مقتطفات بحث؛ لم تتم قراءة صفحاتها كاملة.')
    result['warnings']=list(dict.fromkeys(result['warnings']))[:8]
    result['status']='ok' if result['results'] else 'no_results'
    return result
