"""Flask/Gunicorn application factory adapted from the Oasis site implementation."""
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime
from flask import Flask,g,request,jsonify,redirect,send_from_directory
from werkzeug.exceptions import HTTPException
from clarke import core,db,security,validation,locations,auth,repairs,uploads,admin,mail,maintenance

BASE=Path(__file__).resolve().parent

def create_app(config=None):
    app=Flask(__name__,static_folder=None)
    names=('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','INITIAL_ADMIN_EMAIL','OPERATOR_EMAIL','SESSION_SECRET','ENCRYPTION_KEY','TRUSTED_PROXY_IP')
    app.config.update({name:os.getenv(name,'') for name in names})
    app.config.update(DATA_DIR=os.getenv('DATA_DIR','/data'),PUBLIC_ORIGIN=os.getenv('PUBLIC_ORIGIN','http://127.0.0.1:8787').rstrip('/'),DEMO_MODE=os.getenv('DEMO_MODE','true').lower()=='true',MAX_CONTENT_LENGTH=11*1024*1024,MAX_FORM_MEMORY_SIZE=262144,MAX_FORM_PARTS=3,UPLOAD_MIN_FREE_BYTES=500*1024*1024)
    for name in ('DEMO_ALLOWED_EMAILS','DEMO_ALLOWED_PHONES','NOTIFICATION_EMAILS'):app.config[name]={x.strip().casefold() for x in os.getenv(name,'').split(',') if x.strip()}
    if config:app.config.update(config)
    if not re.fullmatch(r'https?://[^/\s?#]+',app.config['PUBLIC_ORIGIN']):raise RuntimeError('Invalid public origin configuration.')
    initial,alias=app.config['INITIAL_ADMIN_EMAIL'].strip().casefold(),app.config['OPERATOR_EMAIL'].strip().casefold()
    if initial and alias and initial!=alias:raise RuntimeError('Initial administrator configuration disagrees.')
    app.extensions['ready']=False
    with app.app_context():
        db.initialize(app);maintenance.reconcile();app.extensions['ready']=True
    app.before_request(security.guard)
    for blueprint in (locations.bp,auth.bp,repairs.bp,uploads.bp,admin.bp,mail.bp):app.register_blueprint(blueprint)

    @app.errorhandler(core.ApiError)
    def api_error(error):
        data=dict(code=error.code,message=error.message,fields=error.fields,retryable=error.retryable,requestId=getattr(g,'request_id',core.uid()))
        if error.details is not None:data['details']=error.details
        response=jsonify(error=data);response.status_code=error.status
        if error.status in (429,503) or error.code=='IDEMPOTENCY_IN_PROGRESS':response.headers['Retry-After']=str((error.details or {}).get('retryAfterSeconds',3))
        return response

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        code='HOURS_UNAVAILABLE' if request.path=='/api/v1/locations' else 'DATABASE_BUSY'
        return api_error(core.ApiError(code,503,retryable=True))

    @app.errorhandler(Exception)
    def unexpected(error):
        # Human navigation gets a recoverable page; API, private-file and asset
        # failures retain JSON and the actual 404 status.
        path=request.path
        if (isinstance(error,HTTPException) and error.code==404
                and request.method in ('GET','HEAD') and request.accept_mimetypes['text/html']>0
                and not path.startswith(('/api','/oauth','/uploads','/data','/.'))
                and '.' not in path.rsplit('/',1)[-1]
                and (BASE/'dist'/'not-found.html').is_file()):
            response=send_from_directory(BASE/'dist','not-found.html')
            response.status_code=404
            return response
        if isinstance(error,HTTPException):return api_error(core.ApiError('UPLOAD_TOO_LARGE' if error.code==413 else 'NOT_FOUND' if error.code==404 else 'UNSUPPORTED_MEDIA_TYPE' if error.code==415 else 'MALFORMED_JSON',error.code))
        # Only safe type/request IDs are logged. Never SQL, bodies, contacts or OAuth codes.
        app.logger.error('Request failure type=%s request=%s',type(error).__name__,getattr(g,'request_id','none'))
        if app.testing:raise error
        return api_error(core.ApiError('INTERNAL_ERROR',500))

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','Vary':'Cookie','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow','X-Frame-Options':'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; font-src 'self'; img-src 'self' blob: data:; media-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; frame-src 'self'; form-action 'self' https://accounts.google.com"})
        return security.cookie(response)

    @app.get('/health')
    def health():
        try:
            with db.connect() as c:c.execute('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1').fetchone()
            if not app.extensions['ready']:raise RuntimeError()
            return jsonify(status='ok')
        except Exception:return jsonify(status='unavailable'),503

    @app.get('/version.json')
    def version():
        path=BASE/'revision.txt'
        return jsonify(revision=path.read_text().strip() if path.exists() else os.getenv('APP_REVISION','unknown'))

    @app.get('/api/v1/bootstrap')
    def bootstrap():
        with db.transaction() as c:
            security.limit(c,'bootstrap',security.trusted_ip(),120,60000)
            if not getattr(g,'session',None):security.new_session(c)
            s=db.settings(c)
        return core.ok(dict(csrfToken=g.csrf,serverTime=core.iso(core.now()),today=datetime.fromtimestamp(core.now()/1000,validation.NY).date().isoformat(),timezone='America/New_York',intake=dict(accepting=s['intakeAccepting'],message=s['intakePauseMessage']),googleReady=bool(app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET']),uploadLimits=dict(maxFiles=5,maxBytesEach=10485760,mimeTypes=['image/jpeg','image/png','image/webp','image/heic','image/heif']),consentText='Your photos and details are used only to answer this repair request.',consentVersion='repair-intake-v1'))

    @app.get('/robots.txt')
    def robots():return 'User-agent: *\nDisallow: /\n',200,{'Content-Type':'text/plain'}

    @app.get('/')
    @app.get('/<path:path>')
    def page(path=''):
        full='/'+path
        public={'/','/repair-request','/repair-request/complete','/repair-status','/admin/login','/admin/invite','/about','/services','/our-work','/visit','/privacy'}
        staff={'/admin/requests','/admin/requests/new','/admin/settings','/admin/locations','/admin/notices','/admin/team','/admin/emails','/admin/audit'}
        private=full in staff or bool(re.fullmatch(r'/admin/(?:requests|emails/outbox)/[0-9a-f-]{36}',full))
        if private:
            if not getattr(g,'member',None):return redirect('/admin/login',303)
            if not full.startswith('/admin/requests') and g.member['role']!='admin':return 'Admin access is required.',403
        if private or full in public:
            shell='admin.html' if full.startswith('/admin/') else 'repair-request.html' if full.startswith('/repair-request') else 'repair-status.html' if full=='/repair-status' else 'index.html'
            return send_from_directory(BASE/'dist',shell)
        if path.startswith(('api','oauth','uploads','data','.')) or '..' in path.split('/'):raise core.ApiError('NOT_FOUND',404)
        return send_from_directory(BASE/'dist',path)

    return app

if __name__=='__main__':
    logging.getLogger('werkzeug').disabled=True
    create_app().run(host='0.0.0.0',port=int(os.getenv('PORT','8081')),debug=False)
