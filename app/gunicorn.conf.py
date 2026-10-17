import threading
import time

bind='0.0.0.0:8080'
workers=1
threads=4
timeout=45
worker_tmp_dir='/tmp'
accesslog=None
errorlog='-'
capture_output=False

def post_worker_init(worker):
    app=worker.wsgi
    def jobs():
        from clarke import uploads,mail,maintenance
        next_cleanup=0
        while True:
            with app.app_context():
                try:
                    uploads.process_one()
                    mail.drain_one()
                    mail.revoke_one()
                    if time.monotonic()>=next_cleanup:
                        maintenance.reconcile();next_cleanup=time.monotonic()+900
                except Exception:worker.log.error('Background work needs review; no sensitive details logged.')
            time.sleep(1)
    threading.Thread(target=jobs,daemon=True,name='clarke-jobs').start()
