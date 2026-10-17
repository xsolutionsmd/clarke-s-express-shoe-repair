"""Only sourced hours and credential-free operational defaults."""
import json
import uuid

def apply(c, config, stamp):
    initial, alias = config.get('INITIAL_ADMIN_EMAIL','').strip().casefold(), config.get('OPERATOR_EMAIL','').strip().casefold()
    if initial and alias and initial != alias:
        raise RuntimeError('Initial administrator configuration disagrees.')
    initial = initial or alias
    settings = dict(intakeAccepting=True,intakePauseMessage=None,notificationEmails=sorted(config['NOTIFICATION_EMAILS']),emailDeliveryEnabled=False,responseExpectation=None,photoRetentionDays=180,closedLinkDays=90)
    c.execute('INSERT INTO settings VALUES(1,1,?,NULL,?)',(json.dumps(settings),stamp))
    days=[None,None]+[dict(open='09:00',close='17:00') for _ in range(4)]+[dict(open='10:00',close='13:00')]
    c.execute("INSERT INTO hours VALUES('bel_air',1,'America/New_York',?,?)",(json.dumps(days),stamp))
    c.execute("INSERT INTO integration_secrets(name,state) VALUES('gmail','disconnected')")
    if initial:
        c.execute("INSERT INTO members(id,email_norm,role,joined_at,updated_at) VALUES(?,?,'admin',?,?)",(str(uuid.uuid4()),initial,stamp,stamp))
    c.executemany('INSERT INTO app_meta VALUES(?,?)',[('bootstrap_provisioned','true'),('schema_compatibility','1'),('environment_identity',config['PUBLIC_ORIGIN'])])
