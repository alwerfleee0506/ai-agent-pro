"""Real Flask request/renderer tests with only DB and external APIs replaced."""
import ast
import base64
import contextlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from docx import Document
from openpyxl import load_workbook
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from test_invoice import sample

def load_app():
    name='pro_test_app';mod=types.ModuleType(name);mod.__file__=str(ROOT/'app.py');sys.modules[name]=mod
    tree=ast.parse((ROOT/'app.py').read_text())
    # Omit only automatic DB initialization; all production routes and security hooks stay enabled.
    tree.body=[n for n in tree.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='initialize_database')]
    with patch.dict(os.environ,{'PRO_PASSWORD':'Test1234','PRO_SECRET_KEY':'a'*48,'GROQ_API_KEY':'test'}):exec(compile(tree,str(ROOT/'app.py'),'exec'),mod.__dict__)
    return mod

class Cursor:
    def __init__(self,rows):self.rows=rows;self.sql=''
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def execute(self,sql,params=None):self.sql=sql
    def fetchone(self):return {'id':1}
    def fetchall(self):return list(reversed(self.rows))
class DB:
    def __init__(self,rows):self.rows=rows
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def cursor(self,**kw):return Cursor(self.rows)

class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m=load_app()
    def setUp(self):
        self.m=self.__class__.m;self.client=self.m.app.test_client();self.patches=[]
        with self.client.session_transaction() as session:session.update(authenticated=True,csrf_token='test-csrf')
        for name,value in {'DB_SCHEMA_READY':True,'security_rate_limit':lambda *a:None,'security_rate_limit_many':lambda *a:None,'feature_conversation':lambda *a:'test-conversation','get_db':lambda:DB(self.rows),'get_memories':lambda *a:[],'photo_context':lambda:'','handle_photo_message':lambda *a,**kw:None}.items():
            p=patch.object(self.m,name,value);p.start();self.patches.append(p)
        self.rows=[]
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def post(self,data):
        self.rows=[{'role':'user','message':data['message']}]
        return self.client.post('/chat',json=data,headers={'X-PRO-CSRF':'test-csrf'})
    def test_automatic_search_reaches_response_with_source_ids(self):
        def model(*a,**kw):
            if kw.get('plan_only'):return json.dumps({'query':'Samsung S26 Ultra','queries':[]})
            self.assertIsNotNone(kw.get('search_context'))
            return json.dumps({'reply':'المواصفات الرسمية [1]','memories':[],'forget':[]})
        def http(*a,**kw):return types.SimpleNamespace(status_code=200,json=lambda:{'organic':[{'title':'Samsung','link':'https://samsung.com/s26','snippet':'Specs'}]})
        with patch.object(self.m,'call_groq',model),patch.object(self.m,'SERPER_API_KEY','test'),patch.object(self.m,'TAVILY_API_KEY',''),patch.object(self.m.requests,'post',http):
            r=self.post({'message':'شنو مواصفات Samsung S26 Ultra؟'})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['sources'][0]['id'],1)
    def test_invoice_chat_never_lets_model_rewrite_numbers(self):
        b=io.BytesIO();Image.new('RGB',(20,20),'white').save(b,'JPEG');image='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
        calls=[]
        def model(*a,**kw):calls.append(kw);self.assertTrue(kw.get('invoice_mode'));return json.dumps(sample())
        with patch.object(self.m,'call_groq',model):r=self.post({'message':'حول الفاتورة إلى اكسل','images':[image]})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(len(calls),2)
        self.assertEqual(r.json['invoice_review']['calculated_total'],'33000.000');self.assertIsNone(r.json.get('file'))
    def test_word_create_then_short_edit_uses_real_file(self):
        specs=[{'action':'create','format':'docx','title':'تقرير العمل','paragraphs':['الكمية 40']},{'action':'edit','format':'docx','replacements':[{'old':'40','new':'50'}]}]
        def model(*a,**kw):return json.dumps({'reply':'','file_action':specs.pop(0)})
        with patch.object(self.m,'call_groq',model):
            first=self.post({'message':'جهز ملف ورد'});self.assertEqual(first.status_code,200,first.json)
            file=first.json['file'];r=self.post({'message':'عدلها إلى 50','document':{'name':file['name'],'data':file['data']}})
        self.assertEqual(r.status_code,200,r.json)
        doc=Document(io.BytesIO(base64.b64decode(r.json['file']['data'])));self.assertIn('الكمية 50',[p.text for p in doc.paragraphs])
    def test_xlsx_edit_keeps_formula_and_sheet_direction(self):
        from openpyxl import Workbook
        w=Workbook();w.active.title='PRO';w.active['B2']=4;w.active['C2']=13;w.active['D2']='=B2*C2';b=io.BytesIO();w.save(b)
        spec={'action':'edit','format':'xlsx','cells':[{'sheet':'PRO','cell':'B2','value':40}],'sheet_layouts':[{'sheet':'PRO','right_to_left':True}]}
        with patch.object(self.m,'call_groq',lambda *a,**kw:json.dumps({'reply':'','file_action':spec})):
            r=self.post({'message':'خلي الكمية 40 والصنف من اليمين','document':{'name':'invoice.xlsx','data':base64.b64encode(b.getvalue()).decode()}})
        self.assertEqual(r.status_code,200,r.json);ws=load_workbook(io.BytesIO(base64.b64decode(r.json['file']['data']))).active
        self.assertEqual(ws['B2'].value,40);self.assertEqual(ws['D2'].value,'=B2*C2');self.assertTrue(ws.sheet_view.rightToLeft)
    def test_image_edit_sends_all_references(self):
        calls=[];b=io.BytesIO();Image.new('RGB',(10,10)).save(b,'PNG');encoded=base64.b64encode(b.getvalue()).decode()
        def http(*a,**kw):calls.append(kw);return types.SimpleNamespace(status_code=200,json=lambda:{'data':[{'b64_json':encoded}]})
        with self.m.app.test_request_context(),patch.object(self.m.requests,'post',http):
            result=self.m.create_openai_image('عدّل اللون','',[('png',b.getvalue()),('png',b.getvalue())])
        self.assertEqual(len(calls[0]['files']),2);self.assertTrue(all(key=='image[]' for key,_ in calls[0]['files']))
        self.assertEqual(self.m.app.make_response(result).status_code,200)
    def test_auth_and_csrf_still_required(self):
        self.assertEqual(self.client.post('/chat',json={'message':'تمام'}).status_code,403)
        client=self.m.app.test_client();self.assertEqual(client.post('/chat',json={'message':'تمام'}).status_code,401)
    def test_ui_renders_and_new_chat_does_not_load_history(self):
        with self.m.app.test_request_context():html=self.m.render_template_string(self.m.HTML,page='chat',page_title='PRO',csrf_token='test',ui_version=self.m.PRO_UI_VERSION)
        script=re.search(r'<script[^>]*>(.*?)</script>',html,re.S).group(1);Path(tempfile.gettempdir(),'pro_review_ui_check.js').write_text(script)
        self.assertIn('if(PRO_PAGE===\'chat\'){resetDraft();await refreshDue();return}',script)
        self.assertIn('متابعة تعديل هذا الملف',script)
        show_file=script[script.index('function showFile('):script.index('function waitEvent(')]
        self.assertNotIn('pendingDocument=',show_file.split("reuse.addEventListener")[0])

if __name__=='__main__':unittest.main()
