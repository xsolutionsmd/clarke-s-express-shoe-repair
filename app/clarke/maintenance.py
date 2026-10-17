"""Idempotent retention and exact-id synthetic purge. No HTTP entrypoint."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from flask import current_app
from .core import DAY,now,audit,uid
from .db import connect,transaction,settings,save_settings
from .uploads import queue_delete,storage

def reconcile():
    stamp=now()
    with transaction() as c:
        setting=c.execute('SELECT * FROM settings WHERE id=1').fetchone()
        if setting['pending_retention']:
            pending=json.loads(setting['pending_retention'])
            if datetime.fromisoformat(pending['effectiveAt'].replace('Z','+00:00')).timestamp()*1000<=stamp:
                values=settings(c);values.update({k:pending[k] for k in ('photoRetentionDays','closedLinkDays')});save_settings(c,values);audit(c,'retention.activated','settings','1')
        photo_days=settings(c)['photoRetentionDays']
        for photo in list(c.execute("SELECT p.* FROM photos p JOIN drafts d ON d.id=p.draft_id LEFT JOIN requests r ON r.id=p.request_id WHERE p.state<>'deleted' AND ((p.request_id IS NULL AND (d.expires_at<=? OR d.state='deleted')) OR (r.closed_at IS NOT NULL AND r.closed_at<=?))",(stamp,stamp-photo_days*DAY))):queue_delete(c,photo)
        for p in list(c.execute("SELECT * FROM photos WHERE state IN ('uploading','processing') AND lease_expires_at<=?",(stamp,))):
            if p['raw_key']:c.execute('INSERT OR IGNORE INTO file_deletions(id,photo_id,storage_key,queued_at) VALUES(?,?,?,?)',(uid(),p['id'],p['raw_key'],stamp))
            c.execute("UPDATE photos SET state='rejected',raw_key=NULL,error_code='IMAGE_INVALID',processing_lease=NULL WHERE id=?",(p['id'],))
        c.execute("UPDATE drafts SET state='deleted',receipt_cipher=NULL WHERE expires_at<=?",(stamp,))
        c.execute('DELETE FROM oauth_states WHERE expires_at<? OR consumed_at<?',(stamp-3600000,stamp-3600000))
        c.execute('DELETE FROM sessions WHERE (absolute_expires_at<? OR idle_expires_at<? OR revoked_at<?) AND sid_hash NOT IN (SELECT sid_hash FROM oauth_states)',(stamp-DAY,stamp-DAY,stamp-DAY))
        c.execute('UPDATE invitations SET encrypted_token=NULL WHERE expires_at<=? OR accepted_at IS NOT NULL OR revoked_at IS NOT NULL',(stamp,))
        c.execute('DELETE FROM idempotency WHERE expires_at<? AND tombstone=0',(stamp,))
        c.execute('UPDATE idempotency SET encrypted_response=NULL WHERE expires_at<? AND tombstone=1',(stamp,))
        c.execute('DELETE FROM rate_limits WHERE expires_at<=?',(stamp,))
        c.execute("UPDATE outbox SET body_cipher=NULL WHERE updated_at<? AND status IN ('sent','preview_only','cancelled','failed','uncertain')",(stamp-90*DAY,))
        c.execute('UPDATE revocations SET encrypted_token=NULL,outcome=COALESCE(outcome,\'expired\') WHERE expires_at<=?',(stamp,))
        # Minimal audit retained for one year. Requests and customer history are never auto-purged.
        c.execute('DELETE FROM audit_events WHERE created_at<?',(stamp-365*DAY,))
        c.execute('DELETE FROM outbox_attempts WHERE outbox_id IN (SELECT id FROM outbox WHERE body_cipher IS NULL AND updated_at<?)',(stamp-365*DAY,))
        c.execute('DELETE FROM outbox WHERE body_cipher IS NULL AND updated_at<?',(stamp-365*DAY,))
        c.execute('DELETE FROM invitations WHERE expires_at<? AND id NOT IN (SELECT invite_id FROM outbox WHERE invite_id IS NOT NULL) AND token_hash NOT IN (SELECT invite_hash FROM oauth_states WHERE invite_hash IS NOT NULL)',(stamp-365*DAY,))
    with connect() as c:pending=list(c.execute('SELECT * FROM file_deletions WHERE completed_at IS NULL'))
    for deletion in pending:
        # The queue marks photos inaccessible under the same DB lock as attachment.
        try:
            path=storage(deletion['storage_key'])
            if path.exists():path.unlink()
        except (OSError,ValueError):
            with transaction() as c:c.execute('UPDATE file_deletions SET attempts=attempts+1 WHERE id=?',(deletion['id'],))
        else:
            with transaction() as c:c.execute('UPDATE file_deletions SET completed_at=?,attempts=attempts+1 WHERE id=?',(stamp,deletion['id']))
    with transaction() as c:
        for p in list(c.execute("SELECT * FROM photos WHERE state='ready'")):
            if not p['sanitized_key'] or not storage(p['sanitized_key']).is_file():c.execute("UPDATE photos SET state='unavailable',error_code='PHOTO_UNAVAILABLE' WHERE id=?",(p['id'],))
        referenced={r[0] for r in c.execute('SELECT raw_key FROM photos WHERE raw_key IS NOT NULL UNION SELECT sanitized_key FROM photos WHERE sanitized_key IS NOT NULL')}
        root=Path(current_app.config['DATA_DIR'])/'uploads'
        for directory in ('quarantine','sanitized'):
            for path in (root/directory).iterdir():
                key=directory+'/'+path.name
                if key in referenced or path.is_symlink() or not path.is_file():continue
                cutoff=stamp-(300000 if directory=='quarantine' or path.suffix=='.part' else DAY)
                if path.stat().st_mtime*1000<=cutoff:
                    try:storage(key).unlink()
                    except (OSError,ValueError):continue

def purge_synthetic(ids):
    if not ids:raise ValueError('Explicit synthetic request IDs are required.')
    with transaction() as c:
        for ident in ids:
            r=c.execute('SELECT * FROM requests WHERE id=?',(ident,)).fetchone()
            if not r or not r['is_synthetic']:raise ValueError('Refusing a missing or unmarked request.')
        for ident in ids:
            for p in list(c.execute('SELECT * FROM photos WHERE request_id=?',(ident,))):queue_delete(c,p)
    reconcile()
    with transaction() as c:
        for ident in ids:
            if not c.execute('SELECT 1 FROM requests WHERE id=? AND is_synthetic=1',(ident,)).fetchone():raise ValueError('Synthetic marker changed.')
            if c.execute('SELECT 1 FROM file_deletions WHERE completed_at IS NULL AND photo_id IN (SELECT id FROM photos WHERE request_id=?)',(ident,)).fetchone():
                raise RuntimeError('Synthetic photo cleanup is incomplete; retry after resolving storage access.')
            c.execute('DELETE FROM file_deletions WHERE photo_id IN (SELECT id FROM photos WHERE request_id=?)',(ident,))
            c.execute('DELETE FROM outbox_attempts WHERE outbox_id IN (SELECT id FROM outbox WHERE request_id=?)',(ident,))
            c.execute('DELETE FROM outbox WHERE request_id=?',(ident,))
            c.execute('DELETE FROM idempotency WHERE entity_id=? OR entity_id IN (SELECT id FROM offers WHERE request_id=?) OR entity_id IN (SELECT id FROM notes WHERE request_id=?) OR entity_id IN (SELECT id FROM drafts WHERE request_id=?) OR entity_id IN (SELECT id FROM photos WHERE request_id=?)',(ident,ident,ident,ident,ident))
            c.execute('UPDATE requests SET current_offer_id=NULL WHERE id=?',(ident,))
            for table in ('request_events','customer_responses','offers','notes','photos','drafts'):c.execute(f'DELETE FROM {table} WHERE request_id=?',(ident,))
            c.execute('DELETE FROM requests WHERE id=?',(ident,));audit(c,'synthetic.purged','request',ident)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['reconcile','purge-synthetic']);parser.add_argument('--request-id',action='append',default=[]);args=parser.parse_args()
    from server import create_app
    app=create_app()
    with app.app_context():
        if args.action=='reconcile':reconcile()
        else:purge_synthetic(args.request_id)
    print('Maintenance completed.')

if __name__=='__main__':main()
