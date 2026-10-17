import os
import time
import pytest
from playwright.sync_api import sync_playwright
import seed_sessions

BASE=os.environ.get('BASE_URL','http://candidate:8080')

@pytest.fixture(scope='session')
def browser():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--disable-dev-shm-usage'])
        yield browser
        browser.close()
    seed_sessions.exports()

@pytest.fixture(params=[1440,375],ids=['desktop','phone'])
def context(browser,request):
    seed_sessions.reset_business()
    context=browser.new_context(viewport={'width':request.param,'height':900},base_url=BASE,reduced_motion='reduce')
    yield context
    context.close()

@pytest.fixture
def page(context):
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    yield page
    assert not errors,'Browser exceptions: '+repr(errors)

@pytest.fixture
def admin(context):
    identity=seed_sessions.seed('admin');context.add_cookies([identity['cookie']])
    return identity

def mutate(page,path,payload,method='POST',bearer=None,draft=None,key=None):
    import uuid
    return page.evaluate('''async ({path,payload,method,bearer,draft,key}) => {
      const bootstrap = await fetch('/api/v1/bootstrap').then(r=>r.json());
      const headers={'Content-Type':'application/json','X-CSRF-Token':bootstrap.data.csrfToken,'Idempotency-Key':key};
      if(bearer) headers.Authorization='Bearer '+bearer;
      if(draft) headers['X-Draft-Token']=draft;
      const r=await fetch('/api/v1'+path,{method,headers,body:JSON.stringify(payload)});
      return {status:r.status,body:r.status===204?null:await r.json()};
    }''',dict(path=path,payload=payload,method=method,bearer=bearer,draft=draft,key=key or str(uuid.uuid4())))

def read(page,path,bearer=None):
    return page.evaluate('''async ({path,bearer})=>{
      const r=await fetch('/api/v1'+path,{headers:bearer?{Authorization:'Bearer '+bearer}:{}});
      return {status:r.status,body:await r.json()};
    }''',dict(path=path,bearer=bearer))
