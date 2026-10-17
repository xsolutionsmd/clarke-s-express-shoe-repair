# Clarke's Express Shoe Repair — API and data contract

Contract revision: **1**, 2026-10-17. This is the committed interface for the
functional build, not evidence that an endpoint, integration or acceptance test
works. The source specification is [kb/features.md](../kb/features.md), read in
full at parent checkpoint `2da5e1fe90cbb64fbebec68e950ec78280653e4a`.
All **45 pre-release and 13 live rows remain fail/unverified** until actually run.
Changes to this contract go through the backend owner before either consumer changes.

## Scope, decisions and source baseline

Build only `repair-request`, `repair-status`, `staff-admin`, `location-notices`.
Integrate the verified phone/text, Maps, social links and connected Gmail sender.
No booking, availability slots, calendar, payment, SMS provider, mail-in workflow,
public price list or inferred turnaround commitment. Every repair is performed at
Bel Air. Dundalk requests ask for contact to arrange a visit; they never reserve or
confirm a time. Preserve `DEMO_MODE=true` everywhere until separately approved.

Business seeds come from [contact and hours](../kb/contact-and-hours.md),
[offerings](../kb/offerings.md) and their [sources](../kb/sources.md), especially
S1/S4/S14/S15. The feature spec supersedes the earlier research brief's unselected
feature suggestions; template notes can refine presentation without changing this API.

Explicit resolutions of ambiguities (implementation decisions, not owner policies):

| Issue | Binding resolution |
|---|---|
| Short `CLK-7Q4M2` illustration plus phone-last-four is weak | Replace the illustration with a 130-bit opaque reference (26 random Crockford Base32 symbols, grouped for copying). Lookup always requires that complete reference **and** email or phone-last-four. No short searchable public alias. |
| “No prices anywhere public” versus private estimate/status pages | No catalog prices or seeded production estimates. A capability-protected, noindex status page may show only that request's staff-entered estimate. Test amounts are synthetic fixtures, never defaults. |
| “Declines and asks for a call” acceptance wording | Test decline and request-call on separate offers/tickets. Exactly one of `accept`, `decline`, `request_call` is allowed per offer. A new offer is necessary to respond again. |
| Response to `needs_visit` without an estimate | Use a non-monetary visit offer with the same immutable offer ID and one-response rule; it never invents an amount. |
| All admin routes require login, but login/bootstrap must work | Every `/api/v1/admin/*` route, including session, requires a valid staff session. Anonymous CSRF bootstrap and Google start live under `/api/v1/bootstrap` and `/api/v1/auth/*`. `/admin/login` is the public sign-in shell. |
| “Viewer read-only” for hours/notices versus settings access denied | Viewer sees the public location state and request data; management routes/pages for settings, hours, notices, team and full outbox are Admin-only (403). Viewer can operate requests and see delivery badges on their detail. |
| Preview-only guidance versus live demo email acceptance | Default is preview-only. An Admin may enable Gmail delivery; demo sends are then permitted **only** to the private exact test allowlist, including alerts, invites and manual texts. No public demo banners. |
| Staff move backward/forward | Any target status is possible with version checks and required data, but offers are created through offer endpoints; stale offers cannot be revived by a status patch. Closing/reopening rules below apply. |
| Walk-in “contact” with optional email | Require at least email or phone; phone-only tickets work, with a printable reference/status slip. Public submissions still require email. |
| Optional timing target in settings, with no supported promise | Provide nullable `responseExpectation` as staff-only planning text in v1; public copy stays the non-promissory reviewed wording. Publishing a service-time promise requires a later owner-approved contract change. |

### Reused implementation and concrete stack

Inspected the actual Oasis `site` checkout on `abdul-dev` at
`d16f5a99bc2b7d852254564512328fde6b86ddb6` (not the separate stateless design preview).
Reuse its `app/server.py` application factory, parameterized SQLite transactions,
Google state/nonce/PKCE flow, verified Google identity and role/version checks,
Fernet-encrypted Gmail tokens, transactional outbox and uncertain-send treatment;
`app/gunicorn.conf.py` supplies the bounded outbox worker pattern. Its
`app/tests/test_app.py`, `app/backup.py` and existing Clarke `server/` recovery tests
are starting points. Do not copy restaurant models, pricing, branding or credentials.
This contract adds stricter last-admin protection, server sessions, durable
idempotency, version conflicts, image processing and privacy projections.

Use Python **3.12**, Flask **3.1**, Gunicorn **23**, stdlib SQLite and `zoneinfo`,
`google-auth`, `requests`, `itsdangerous`, `cryptography`/Fernet, Pillow with
`pillow-heif`/libheif and `phonenumbers` for phone validation. Pin tested patch
versions and hashes during backend work;
do not blindly transplant Oasis's entire dated lock. Use the existing Vite **7** /
Node **22** builder for HTML, CSS and browser ES modules. Node is build/dev-only;
Flask serves compiled `app/dist` in runtime. No Redis or second database/service.
SQLite and sanitized images live on the existing independent `/data` mount.

Google flow implementation follows the [Google web-server OAuth reference](https://developers.google.com/identity/protocols/oauth2/web-server).
The decoder choice uses [Pillow-Heif](https://pillow-heif.readthedocs.io/en/latest/);
pixel limits and decoding failures must be enforced explicitly, as described in
[Pillow's Image reference](https://pillow.readthedocs.io/en/stable/reference/Image.html).
These libraries are not a claim that any image is safe without the isolation below.

### File and runtime ownership for the next stage

| Owner | Exclusive paths / boundary |
|---|---|
| Frontend (Opus) | `app/index.html`, `app/src/**`, `app/public/**`, `app/package.json`, `app/package-lock.json`, `app/vite.config.mjs`; customer/admin UI, client API wrapper, styles, assets, browser draft storage. `app/dist` is generated/ignored. |
| Backend (Astra) | `app/server.py`, `app/wsgi.py`, `app/gunicorn.conf.py`, `app/clarke/**`, `app/migrations/**`, `app/requirements*.txt`, `app/tests/**`, `tests/e2e/**`, `Dockerfile`, `runtime/**`, Compose files, `scripts/app.py`, focused backend/check/deployment wiring, this contract. Coordinate integration changes before touching frontend-owned files. |
| Parent/coordinator | `AGENTS.md`, `kb/HANDOFF.md`, `xsolutions.json`, pipeline/XC records, final validation/release coordination. Template owner alone edits `kb/design-brief.md` and Template flow notes in `kb/features.md`. |

Frontend builds via `npm ci && npm run build` to `app/dist`; Vite dev listens on
**8080**, proxies `/api/`, `/oauth/`, `/health`, `/version.json` to Flask on
**127.0.0.1:8081** inside the development container. Bind frontend port 8080 to
host **127.0.0.1:8787** through the existing launcher. Production serves everything
on **8080** with one Gunicorn worker/four threads and a single serialized image
decoder; no additional published port. Start route stays `./app.ps1 start` or
`bash app.sh start`, then `http://127.0.0.1:8787/`; admin `/admin/login`.
Do not allocate ports or start an environment during this contract-only stage.

Preserve UID/GID **10001**, read-only root filesystem, 256 MB / 100 PID limits,
existing health/revision labels, independent keys/volumes/OAuth clients, Caddy
55 MB request ceiling, backups and updater rollback behavior. Runtime must install
**wget** so the existing network-isolated candidate probe still works. Preserve
`/health` and uncached `/version.json` (see runtime section). Docker build targets
remain `development`, `test`, `runtime`; add `e2e` in implementation.

## Wire conventions and errors

Base path `/api/v1`. JSON is UTF-8; `Content-Type: application/json` required on
JSON mutations, max **32 KiB**. Reject unknown fields; enums are case-sensitive.
No JSONP or permissive CORS. All API responses and private pages: `Cache-Control:
no-store`, `Vary: Cookie`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`. Private pages have no third-party scripts/resources.
All examples below are synthetic, use `example.test`, and are not credentials.
ISO timestamps are UTC RFC3339 ending `Z`; date-only fields are `YYYY-MM-DD` in
`America/New_York`. IDs are opaque UUIDs (prefixed display placeholders below are
illustrative only). Money is integer USD cents, never floating point.

Success envelope is `{"data":{}}`, with data replaced by the endpoint's object.
List shape is always
`{"data":{"items":[],"nextCursor":null}}`; no hidden pagination. Page size defaults
25, max 100; cursor is an opaque signed keyset cursor bound to the query/filter,
valid for 30 minutes. Bad/expired cursor: 400 `INVALID_CURSOR`; reset to first page.
The cursor also binds its resource and authenticated member or status capability;
changing filters, principal or capability requires starting at the first page.
Request ID is a random `X-Request-ID` response header, also in errors.

Every error uses this shape, including framework/body-limit/auth errors:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Check the highlighted fields.",
    "fields": {"description": "Enter 10–2000 characters."},
    "retryable": false,
    "requestId": "c7d06238-730c-45cf-8d7a-f47283633d98",
    "details": {}
  }
}
```

`fields` keys use dotted paths such as `contact.phone`, `photoIds`, `days.2.close`;
empty errors use `{}`. Never echo submitted PII, tokens, SQL, raw provider errors,
filesystem paths or tracebacks. Proxy 413/network errors may lack JSON; client
still preserves input and renders its safe fallback. `details` only contains the
documented machine-readable values below.

| HTTP | Codes / behavior |
|---|---|
| 200 / 201 / 202 / 204 | Read/update/replay; created; queued/processing; empty successful deletion/logout. |
| 400 | `MALFORMED_JSON`, `INVALID_CURSOR`, `INVALID_IDEMPOTENCY_KEY`. |
| 401 | `AUTH_REQUIRED` / `SESSION_EXPIRED`; staff draft retained, then sign-in. |
| 403 | `FORBIDDEN`, `CSRF_INVALID`, `ORIGIN_DENIED`, `ACCOUNT_NOT_INVITED`, `INVITE_ACCOUNT_MISMATCH`, `DEMO_DESTINATION_BLOCKED`. |
| 404 | `NOT_FOUND`, `PHOTO_UNAVAILABLE`; public status/lookup uses only `STATUS_UNAVAILABLE` with identical text for invalid, expired, deleted or mismatched credentials. |
| 409 | `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `IDEMPOTENCY_IN_PROGRESS`, `RESPONSE_ALREADY_RECORDED`, `OFFER_SUPERSEDED`, `INVALID_TRANSITION`, `PHOTOS_NOT_READY`, `DRAFT_EXPIRED`, `DRAFT_SUBMITTED`, `INTAKE_PAUSED`, `LAST_ADMIN`, `MEMBER_EXISTS`, `EMAIL_NOT_RETRYABLE`, `SENDER_DISCONNECTED`. |
| 410 | `INVITE_UNAVAILABLE` for unknown/expired/used/revoked invite, one generic message. Never 410 for public repair lookup. |
| 413 / 415 | `UPLOAD_TOO_LARGE` / `UNSUPPORTED_IMAGE` or `UNSUPPORTED_MEDIA_TYPE`. |
| 422 | `VALIDATION_FAILED`, `IMAGE_INVALID`, `IMAGE_LIMIT_EXCEEDED`, `INVALID_LOCAL_TIME`. |
| 428 | `VERSION_REQUIRED` on a versioned mutation lacking `expectedVersion`. |
| 429 | `RATE_LIMITED`; `Retry-After` seconds and `details.retryAfterSeconds`. |
| 500 | `INTERNAL_ERROR`, sanitized ID; retryable only where idempotency permits. |
| 503 | `DATABASE_BUSY`, `UPLOAD_CAPACITY`, `INTEGRATION_UNAVAILABLE`, `HOURS_UNAVAILABLE`; bounded `Retry-After`, no false success. |

Mutations use CSRF and Origin checks even when public. Authenticate/authorize
before revealing an admin resource or version. For recognized replay keys, return
the original committed result before rechecking current business state, but only
after verifying the original actor/capability is still authorized.

### Sessions, CSRF and abuse limits

`GET /api/v1/bootstrap` creates/refreshes an anonymous session and CSRF token. Cookie
`clarke_session` is a signed opaque session ID, HttpOnly, SameSite=Lax, Path=/,
no Domain, Secure on HTTPS. The server uses `itsdangerous.URLSafeTimedSerializer`
with salt `clarke-session-v1`, payload `{"sid":"<32-byte-base64url>"}`; DB stores
SHA-256 of sid and CSRF token. Signatures expire with the session. Anonymous session
expires after 24h (draft bearer resumes it); staff expires at 12h absolute or 2h
idle, whichever first. Rotate sid/CSRF on login and role change; revoke on logout.
Role and member-version are checked in SQLite on **every** staff call, including
private image fetches. Session DB is the source of truth, not cookie role claims.
Derive the CSRF token as base64url HMAC-SHA256 of raw sid with a domain-separated
CSRF key derived from `secret.key`; store its hash for verification. Bootstrap
and session endpoints can recompute the same token after reload without storing
plaintext CSRF or resetting unrelated tabs. Signature decoding has a 24h ceiling;
DB deadlines impose the shorter staff expiry. Staff session reads may extend idle
expiry only up to the absolute deadline, never extend the 12h login lifetime.

All POST/PUT/PATCH/DELETE calls require `X-CSRF-Token`, valid session cookie and
an exact Origin matching configured `PUBLIC_ORIGIN`; missing Origin is rejected
for browser API writes. OAuth callback instead uses single-use state plus browser
binding, nonce and PKCE. No GET performs a business mutation. Trust forwarded
scheme/IP only from the single configured gateway; ignore arbitrary forwarded IPs.
Local development accepts only its explicitly configured loopback origin. Health
does not need Origin/auth. CSRF refresh is safe once; do not discard the form.

Persist atomic token-bucket limits in SQLite; keys are HMACs of trusted IP/contact,
not raw contact in logs. A server secret derives an environment-specific HMAC key.
Independent defaults (configurable privately, no public policy editor):

| Operation | Limit |
|---|---|
| Bootstrap | 120/min/IP; bounded anonymous sessions, reuse existing cookie |
| Draft creation | 10/hour/IP, max 3 unexpired drafts/session |
| Uploads | 30 files/hour/IP, 200 MiB/hour/IP; 5 active photo slots/draft |
| New online requests | 10/hour/IP, 3/hour/normalized email and supplied phone separately |
| Lookup failures | 10/15min/IP and 5/15min/HMAC(reference); a miss and expired record cost the same |
| Valid capability status read | 60/min/IP and 30/min/token |
| Estimate response | 10/15min/IP and 5/15min/offer; replay not counted twice |
| OAuth/invite attempts | 20/hour/IP; invite start 5/15min/token |
| Staff writes / reads | 60/min/member / 300/min/member |

Replay of a valid submission is not a second contact submission. `website` is the
empty honeypot field; nonempty submissions return generic 422 `VALIDATION_FAILED`
without creating a request, attaching photos or sending mail. No captcha by default;
no Turnstile/network dependency unless explicitly enabled later. Do not hard-lock a
request indefinitely on bad lookup attempts; short buckets expire. Return dial/text
fallback from the already loaded location data.

## Shared values and field validation

| Field | Contract |
|---|---|
| `itemType` | `shoes`, `boots`, `handbag_purse`, `belt_strap`, `leather_garment`, `luggage`, `baseball_glove`, `other_leather`, `keys`; keys label includes “ask us”. |
| `workTypes` | Unique array, 0–10 from `soles_heels`, `heel_tips`, `stretch_fit`, `orthopedic_modification`, `stitching`, `zipper`, `dye_color`, `clean_condition`, `straps_hardware`, `not_sure`; `not_sure` is exclusive. |
| `description` | Required 10–2000 Unicode characters after trim/NFC; plain text. |
| `brandAge` | Optional null or trimmed 1–120 characters. |
| `location` | `bel_air` or `dundalk`; repair-work location always `bel_air`. |
| `neededBy` | Optional null or real local date, today or later; no arbitrary short horizon. Within 0–3 calendar days inclusive adds `TIMING_NOT_CONFIRMED` warning. No requested time. |
| `contact.name` | Required 1–100 trimmed Unicode characters; no markup/control characters. |
| `contact.email` | Required online, optional walk-in; max 254, one syntactically valid address, no display-name/CRLF. Trim and casefold for matching; do not fold dots or plus aliases. No DNS/SMTP existence check. |
| `contact.phone` | Optional online except call/text preference; normalized E.164 max 15 digits; accept US 10 digits/+1/formatting, or explicit international +country code. Reject extensions, alphabetic junk and invalid numbering via pinned phone parser. |
| `contact.preferred` | `email`, `call`, `text`; corresponding address/phone required. Walk-in defaults only when explicitly selected, not from an unstated consent. |
| `photoIds` | Unique array, 0–5, all `ready`, owned by draft, unexpired, not attached elsewhere. |
| `customerMessage` | Public-facing plain text, max 2000; no internal notes or personal contact data in it. |
| `internalNote` | Staff-only plain text, 1–4000; append-only notes. |

Trim/NFC and character bounds apply consistently before hashing idempotency
payloads. Escape all text on HTML/email rendering; no Markdown/HTML from users.
Optional fields use null, not empty strings, in canonical responses. Boolean values
must be actual booleans; reject float-as-integer and string-as-number coercion.

## Public bootstrap, locations and drafts

`GET /api/v1/bootstrap` (anonymous; no body) → 200, full representative response:

```json
{
  "data": {
    "csrfToken": "example-csrf",
    "serverTime": "2026-10-17T14:30:00Z",
    "today": "2026-10-17",
    "timezone": "America/New_York",
    "intake": {"accepting": true, "message": null},
    "googleReady": true,
    "uploadLimits": {"maxFiles": 5, "maxBytesEach": 10485760, "mimeTypes": ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"]},
    "consentText": "Your photos and details are used only to answer this repair request.",
    "consentVersion": "repair-intake-v1"
  }
}
```

No demo flag, staff identity, notification destinations or integration secret in
public bootstrap. Form enums/labels above are shared compile-time constants, not
an owner-editable price or service catalog.

`GET /api/v1/locations` → 200 `data` below; also reused as the `locations` object in
confirmation/status responses (full two-location projection, not private settings):

```json
{
  "data": {
    "asOf": "2026-10-17T14:30:00Z",
    "validUntil": "2026-10-17T14:31:00Z",
    "timezone": "America/New_York",
    "hoursVersion": 1,
    "locations": [
      {
        "id": "bel_air", "name": "Bel Air", "visitMode": "walk_in",
        "address": "23 South Main St. (REAR), Burns Alley, Bel Air, MD 21014",
        "directionsNote": "Behind Boyd Fulford Pharmacy and The Main Street Tower Restaurant. Public parking is in front of the rear shop.",
        "phoneHref": "tel:+14108368316", "smsHref": null,
        "mapsHref": "https://www.google.com/maps/place/Clarke's+Express+Shoe+Repair/data=!4m2!3m1!1s0x0:0x87b61559389294c5",
        "weeklyHours": [null, null, {"open":"09:00","close":"17:00"}, {"open":"09:00","close":"17:00"}, {"open":"09:00","close":"17:00"}, {"open":"09:00","close":"17:00"}, {"open":"10:00","close":"13:00"}],
        "state": "open", "stateText": "Open until 1 pm",
        "closesAt": "2026-10-17T17:00:00Z", "nextOpensAt": null,
        "activeNotice": null, "repairWorkHere": true
      },
      {
        "id": "dundalk", "name": "Dundalk", "visitMode": "appointment_only",
        "address": "6920 Holabird Ave., Dundalk, MD 21222",
        "directionsNote": "By appointment. Call or text to arrange a visit. All repairs are performed in Bel Air.",
        "phoneHref": "tel:+14433863800", "smsHref": "sms:+14433863800",
        "mapsHref": "https://www.google.com/maps/place/Clarke's+Express+Shoe+Repair/data=!4m2!3m1!1s0x89c80135e7828f67:0x9af1bbe4049ffff",
        "weeklyHours": null, "state": "appointment_only",
        "stateText": "By appointment, call or text 443-386-3800",
        "closesAt": null, "nextOpensAt": null, "activeNotice": null,
        "repairWorkHere": false
      }
    ]
  }
}
```

Social destinations are fixed sourced links:
`https://www.facebook.com/clarkesexpressshoerepair/` and
`https://www.instagram.com/clarke_the_shoe_doc/`. No third-party API or Maps embed
is required. Do not reuse the legacy Dundalk phone or fixed hours from old sources.

`POST /api/v1/drafts` with `Idempotency-Key` and body `{}` → 201:

```json
{"data":{"draftId":"8b71286f-ecb8-4c99-8f10-f6d3d620d8af","draftToken":"bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM","state":"active","expiresAt":"2026-10-18T14:30:00Z","photos":[]}}
```

Draft token is 32 random bytes, hash stored, bearer supplied as `X-Draft-Token` on
draft/photo/submit routes, never query string. Draft ID alone grants nothing.
`GET /api/v1/drafts/{draftId}` with that header → 200 same data excluding raw
`draftToken`; `photos` is an array of Photo metadata below. For `submitted`, adds
`receipt` containing the same create-request success payload, during the 24h draft
retention window. No submitted PII is returned. This recovers a lost submit response.
`DELETE /api/v1/drafts/{draftId}` with header/CSRF → 204; active draft only;
submitted returns 409 `DRAFT_SUBMITTED`. It queues disposal, not request deletion.
Unknown/wrong draft returns 404; known expired bearer returns 409 `DRAFT_EXPIRED`.
Expiry is fixed 24h from creation and not extended by polling.

### Upload lifecycle

`POST /api/v1/drafts/{draftId}/photos` with draft header, CSRF and idempotency key:
multipart **one** `file` per request, no additional form parts. Request example:

```http
POST /api/v1/drafts/8b71286f-ecb8-4c99-8f10-f6d3d620d8af/photos
Origin: https://repair.example.test
X-CSRF-Token: example-csrf
X-Draft-Token: bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM
Idempotency-Key: 953da67f-ff23-4209-8801-5c2e8de3f123
Content-Type: multipart/form-data; boundary=clarke-example

--clarke-example
Content-Disposition: form-data; name="file"; filename="shoe.heic"
Content-Type: image/heic

[binary image bytes]
--clarke-example--
```

202 `{"data":{"photoId":"8666e050-c22b-4674-b82b-ae00cb853911","state":"processing","mediaType":null,"width":null,"height":null,"bytes":null,"error":null}}`.
For byte/type/count errors reject immediately; conversion errors appear on polling.
`GET /api/v1/drafts/{draftId}/photos/{photoId}` → 200 Photo:

```json
{"data":{"photoId":"8666e050-c22b-4674-b82b-ae00cb853911","state":"ready","mediaType":"image/jpeg","width":1600,"height":1200,"bytes":184320,"error":null}}
```

States: `uploading`, `processing`, `ready`, `rejected`, `deleted`.
Rejected example: same keys with null output fields, `state:"rejected"`,
`error:{"code":"IMAGE_INVALID","message":"This photo could not be read. Try another photo."}`.
No stored filename, disk path, EXIF, content URL or photo bytes in public APIs.
Local browser file/object URLs provide previews; after refresh show “Photo attached”
with removal, not an inaccessible image. If draft expired, ask for reattachment.
`DELETE /api/v1/drafts/{draftId}/photos/{photoId}` → 204 and frees its slot;
idempotent if already deleted. Submitted/claimed images cannot be removed here.
Poll 1s then 2s/5s, stop when settled or page hidden; GET draft restores all metadata.
Use XHR or equivalent for upload progress; show converting separately after transfer.
If another transfer with the same key is still streaming and its hash is not yet
known, return 409 `IDEMPOTENCY_IN_PROGRESS` with Retry-After 2; retain that reserved
slot and do not allocate another. A later retry compares the complete source hash.

Limits are **5 × 10 MiB** (10,485,760 bytes/file), intentionally defining the
spec's “10 MB”. UI shows the limit without relying on client enforcement. Single
multipart body limit **11 MiB** including overhead, global gateway remains 55 MB.
Stream to randomized private quarantine; never buffer all files in Flask memory.
Accept actual decoded JPEG, PNG, WebP and HEIC/HEIF, checking signatures and decoder
format, not extension/MIME alone. Reject SVG, GIF, AVIF, PDFs, archives, animated
WebP/APNG, multipage/multi-image HEIF, corrupt/truncated data and polyglots that do
not decode cleanly. No client URLs, remote fetching or paths accepted.

Process exactly one image at a time in a non-root decoder subprocess with no
network access and no credential environment; sandbox with an RLIMIT_AS budget of
**160 MiB**, CPU budget 15s and wall budget 20s. Keep Pillow decompression-bomb
errors enabled. Header dimensions cap at **50 megapixels**, 16,384 pixels per edge;
use decoder reduction to <=4096 pixels before full raster materialization where
supported. If a legitimate large image cannot be processed within memory/time
budgets, reject gracefully `IMAGE_LIMIT_EXCEEDED`, explain smaller export, retain
other photos. Test real 12MP HEIC on the 256 MB runtime before claiming acceptance;
HEIC support must not be silently disabled if that test fails.

Apply orientation, composite alpha on white, convert to sRGB RGB, resample max edge
**2048**, encode fresh JPEG quality 85 into a new image with **no EXIF, XMP, IPTC,
ICC, comments, thumbnails or original metadata**. Ignore source filename for storage.
Check output by decoding it again; cap sanitized output at 4 MiB. No original file
is ever served. Re-encoding is containment, not a promise to detect every malware
sample; keep decoder libraries patched and test malformed/oversized inputs.
The decoder sandbox must also prevent filesystem credential reads: preload allowed
decoder libraries, inherit only explicitly opened input/output/result descriptors,
then apply no-new-privileges and a syscall filter denying new file opens, network
sockets, exec and process creation before decoding. Do not rely on stripped env
alone: the web process UID can otherwise read `/data` keys. Fail conversion closed
if that sandbox cannot initialize; test that the child cannot open a key file or
connect a socket. This is an implementation/test obligation within the existing
container, not permission to relax its memory limit or mount secrets elsewhere.

Write output to `/data/uploads/sanitized/{random-id}.jpg`, fsync and atomic rename
on the same filesystem, then mark DB row `ready`. Remove raw quarantine immediately
after processing, success or failure. Store ownership and content hash in DB.
Reservation of a photo slot is transactional to stop concurrent sixth uploads.
Interrupted raw uploads/processing leases with no active heartbeat expire after
5min and become rejected;
ready unclaimed photos and drafts are garbage-collected after 24h. Cleanup runs at
startup and every 15min and reconciles orphan files. Files in use/attached are not
removed; attach/delete/GC take the same SQLite write lock and recheck state.
Stop new uploads at configured storage watermark (default 500 MiB available) with
503 `UPLOAD_CAPACITY`; do not delete application data to free space.

## Create request and preserve drafts

`POST /api/v1/requests` with draft header, CSRF and UUIDv4 `Idempotency-Key`:

```json
{
  "draftId":"8b71286f-ecb8-4c99-8f10-f6d3d620d8af",
  "itemType":"boots", "workTypes":["soles_heels"],
  "description":"The heel has separated from the sole of my left boot.",
  "brandAge":null, "location":"dundalk", "neededBy":"2026-10-20",
  "contact":{"name":"Example Customer","email":"customer@example.test","phone":"+12025550123","preferred":"text"},
  "photoIds":["8666e050-c22b-4674-b82b-ae00cb853911"],
  "consentVersion":"repair-intake-v1", "website":""
}
```

201 (initial) / 200 (identical replay, `Idempotency-Replayed: true`):

```json
{
  "data": {
    "reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP",
    "status":"new", "createdAt":"2026-10-17T14:30:00Z",
    "statusUrl":"https://repair.example.test/repair-status#token=bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM",
    "location":"dundalk", "appointmentConfirmed":false,
    "message":"We've received your repair request. We'll look at your photos and reply with an estimate or ask to see it in person.",
    "locationMessage":"This is a request for contact, not an appointment. Call or text 443-386-3800 to arrange a Dundalk visit. All repairs are performed in Bel Air.",
    "closureMessage":null, "nextOpensAt":null,
    "warnings":[{"code":"TIMING_NOT_CONFIRMED","message":"Timing is confirmed only after we review your request."}],
    "notifications":{"recorded":true}
  }
}
```

Fetch `/locations` for both full location cards; the success payload's closure
message and next opening are server-computed at submission and persisted for
exact replay. No “email sent” or timing guarantee; creation succeeds even if Gmail
is disconnected. Delivery is asynchronous. Intake pause rejects new commits with
409 `INTAKE_PAUSED`, `details:{"message":"Please call or text the shop."}`;
draft/photos remain recoverable until expiry. Existing receipts/status remain usable.

Before submit require every non-deleted, accepted draft photo settled and every
intended photo ID ready. A customer must remove an unwanted/rejected upload before
proceeding; no silent partial attachment. In one `BEGIN IMMEDIATE` transaction:
resolve idempotency, verify pause and limits, lock draft, insert request + public
credentials + initial event, atomically claim ready photos, persist receipt,
mark draft submitted, enqueue customer/staff notifications, commit. No Google/file
conversion work inside that transaction. Rollback leaves the draft and files intact.

Same key + different canonical payload → 409 `IDEMPOTENCY_CONFLICT`. Same draft
with a different key after creation returns its original receipt, never a second
request. Versioned staff creates/writes, offers, responses, retries and invites use
the same idempotency header. Retain encrypted canonical response/payload hash 7d;
creation keys remain tombstoned/hash-linked for the life of the request. Draft
bearer expires at 24h even if receipt retention is longer; later recovery uses
reference/email lookup. Failed validation is not a committed result; preserve key
for correcting the form, but mint a new key after an intentionally different
successful action. Upload payload hash uses streamed file SHA-256, not filename.

Frontend stores schema-versioned intake fields, draft bearer, photo metadata and
submission key in **sessionStorage** (same tab survives refresh/back); TTL 24h,
explicit “Clear draft”, no localStorage/analytics/IndexedDB PII. Retain on offline,
422, 429, 503 and CSRF refresh; never auto-resubmit after returning online. On
success clear contact/intake fields but retain minimal receipt/reference/status
capability until tab close/24h. Browser history uses `/repair-request` and
`/repair-request/complete`, no form fields in URLs. Back after success shows receipt
and explicit “Start another request”, not an enabled stale submit. Files themselves
are not persisted in browser storage; explain reattachment on draft expiry.

## Status capability, lookup and customer response

Generate reference symbols with a CSPRNG: 26 independently uniform Crockford
Base32 characters (130 bits), unique DB constraint/retry. Render `CLK-` and groups
of 5/5/5/5/6; accept case-insensitive compact/hyphenated input and Crockford aliases
O→0, I/L→1. Also generate an independent 32-byte base64url status token (256 bits).
Store HMAC-SHA256 lookup hashes; encrypt raw reference/token only for authorized
staff text/slip and delivery/replay use. Never log credentials or place them in
query strings, path parameters, analytics or provider error messages.

Status URL is `/repair-status#token=<token>`. JS captures the fragment, replaces
history with `/repair-status`, saves token in sessionStorage and sends
`Authorization: Bearer <token>` to status endpoints; fragment is never sent as
Referer. Public status bearer never grants photos, contacts, internal notes or
staff actions. No customer account is introduced.

`POST /api/v1/status/lookup` (anonymous session/CSRF, no bearer):

```json
{"reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP","verification":{"type":"email","value":"customer@example.test"}}
```

Alternative `verification:{"type":"phone_last4","value":"0123"}` (exact four
digits, stored phone must exist). Exactly one verification method. Success 200:

```json
{"data":{"statusToken":"bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM","statusUrl":"https://repair.example.test/repair-status#token=bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM"}}
```

Failure for malformed credentials/mismatch/unknown/expired/deleted uses identical
404 `STATUS_UNAVAILABLE`, message “This request is unavailable. Check your details
or call the shop.” Constant-time hash comparison, same dummy lookup path for misses;
do not return whether email/phone/reference exists or distinguish closed records.
Rate-limit before expensive work; pad processing to a bounded uniform floor
(100–150ms) without holding a database transaction. No phone-only/reference-only
lookup, partial search or public response containing contact fragments.

`GET /api/v1/status` (bearer; no body) → 200:

```json
{
  "data": {
    "reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP", "version":4,
    "status":"estimate_sent", "statusLabel":"Estimate ready",
    "itemType":"boots", "dropoffLocation":"dundalk", "pickupLocation":"dundalk",
    "appointmentConfirmed":false, "updatedAt":"2026-10-17T15:00:00Z",
    "nextAction":"Review the estimate. A Dundalk visit still needs to be arranged by phone or text.",
    "customerMessage":"We can assess the sole repair when you bring the boots in.",
    "offer":{"id":"66c62863-dfe6-479d-b012-d991dd9df088","kind":"estimate","currency":"USD","amountMinCents":1234,"amountMaxCents":2345,"scope":"Example repair scope entered by staff.","timingNote":null,"disclaimer":"Estimate; final price confirmed when we see the item in person.","sentAt":"2026-10-17T15:00:00Z","response":null},
    "allowedResponses":["accept","decline","request_call"],
    "history":[{"id":"66bc0c68-4b87-4ef9-a4e5-a826aa31daa0","type":"received","status":"new","message":"Request received.","at":"2026-10-17T14:30:00Z"},{"id":"a6e7138f-8861-4a62-b020-bb0f2a2ebfe9","type":"offer_sent","status":"estimate_sent","message":"Estimate ready.","at":"2026-10-17T15:00:00Z"}],
    "locationDataUrl":"/api/v1/locations"
  }
}
```

Synthetic cents in this example illustrate shape only. Never auto-seed them.
Projection excludes name/email/phone, description, original filenames/photos,
brand/age, internal notes, staff identity, audit data, outbox body and dates needed
by the customer. Public history contains explicitly customer-visible events only,
old offer amounts excluded. History is chronological, max 50 on this payload;
`GET /api/v1/status/events?cursor=...&limit=25` returns the same event objects in
the common list envelope for older history (bearer required).

`POST /api/v1/status/responses` (bearer + anonymous CSRF + idempotency):

```json
{"offerId":"66c62863-dfe6-479d-b012-d991dd9df088","expectedVersion":4,"choice":"accept","phone":null}
```

200 `{"data":{"responseId":"9c253e41-8190-4483-bb67-45d70f3f7d03","offerId":"66c62863-dfe6-479d-b012-d991dd9df088","choice":"accept","status":"awaiting_dropoff","version":5,"recordedAt":"2026-10-17T15:10:00Z","message":"Response recorded. Call or text 443-386-3800 to arrange a Dundalk visit."}}`.
`decline` closes with `cancelled`. `request_call` requires a phone supplied in this
response, even when one already exists (no phone disclosure); stores it as the
callback number, keeps current status, disables all responses, alerts staff.
`phone` must be null for accept/decline. Response may not silently change customer
contact preference. A new offer, not a status toggle, reopens response actions.
Already answered with a new key → 409 `RESPONSE_ALREADY_RECORDED`; same key returns
original success. Superseded offer → 409 `OFFER_SUPERSEDED`. Refresh status, keep
typed callback phone, and require customer to review a newer offer before retrying.
In a single transaction check offer/current version/status, insert unique response,
change status if applicable, increment request version, append event/audit and
enqueue staff alert. Only `estimate_sent` and `needs_visit` permit a response.

Tokens remain valid while open. Closed = `picked_up` or `cancelled`; expire exactly
90×24h after `closedAt` by default. Invalid and expired links receive the same
generic fallback and lookup/call actions. A correct-but-expired lookup cannot renew
access. On reopening before expiry retain token; after expiry issue new token
and invalidate old, record rotation; staff may share the new link. `not_repairable`
does not silently close: it shows explanation until staff explicitly closes it.

## Google sign-in, initial admin and invitations

Google is the only login. No password, magic-login email, shared credential,
environment-variable bypass, special request header or HTTP fixture endpoint.
Keep all three existing clients and the **exact `/oauth/callback`** callback in
[oracle-contract.json](../deploy/oracle-contract.json); do not add a second callback
for Gmail or broaden authorized origins. `PUBLIC_ORIGIN` is configuration, never
derived from untrusted Host/X-Forwarded-Host.

`POST /api/v1/auth/google/start` with anonymous CSRF:

```json
{"returnTo":"/admin/requests","inviteToken":null}
```

200 `{"data":{"authorizationUrl":"https://accounts.google.com/o/oauth2/v2/auth?client_id=example-client&state=example-state&redirect_uri=https%3A%2F%2Frepair.example.test%2Foauth%2Fcallback","expiresAt":"2026-10-17T14:40:00Z"}}`.
The actual URL includes response type code, `openid email`, nonce, S256 PKCE;
the example omits only generated Google query values, not application JSON fields.
Redirect the browser with `location.assign`. `returnTo` is allowlisted relative
`/admin/...`, max 256, no protocol-relative URL, fragment, query PII or open redirect.
Gmail has a separate authenticated start endpoint below, sharing the callback.

Store one-use OAuth state hash, nonce, verifier (encrypted), purpose, initiating
sid hash, member ID/version (Gmail only), invite hash and return path, expiry **10m**.
Callback validates browser/session state in constant time, consumes state once,
exchanges code with bounded timeout, verifies issuer/audience/expiry/signature,
nonce and `email_verified`, then checks member and Google `sub`. Email alone never
overwrites a bound different sub. No token/code/error description enters logs.
Recheck invitation/admin role transactionally after the network exchange.

`GET /oauth/callback?code=<google-code>&state=<state>` → **303** to stored admin
path on success; sanitized failure 303 `/admin/login?error=<code>` where code is
`signin_cancelled`, `signin_expired`, `account_not_invited`, `invite_unavailable`,
`invite_account_mismatch`, `google_unavailable` or `sender_permission_denied`.
No raw provider message, email or code in redirect. Missing config at start →
503 `INTEGRATION_UNAVAILABLE`; canceled/failed connection does not erase an existing
sender. Pending staff drafts remain in sessionStorage across the same-tab redirect.

Initial bootstrap is **server-only**: on a genuinely new application DB, seed the
single enabled-but-unbound membership (`active=true`, no Google sub) from private
`INITIAL_ADMIN_EMAIL` (fallback
`OPERATOR_EMAIL` only when the first variable is absent). If both differ, refuse
startup with a sanitized configuration error. Seed role Admin and mark
`bootstrap_provisioned` in the same migration transaction; it becomes usable only
after that exact verified Google email signs in and its sub is bound. Never
auto-recreate a removed initial admin on restart. No public initial-admin endpoint
or email field. Initial membership can be removed after another active, verified
Admin exists. No runtime fixtures or sample members.

`GET /api/v1/admin/session` → 200:

```json
{"data":{"member":{"id":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","email":"admin@example.test","role":"admin","version":1},"csrfToken":"example-staff-csrf","expiresAt":"2026-10-18T02:30:00Z","idleExpiresAt":"2026-10-17T16:30:00Z","demoMode":true,"permissions":{"requestsWrite":true,"settingsWrite":true,"teamWrite":true,"emailManage":true}}}
```

Signed out → 401 `AUTH_REQUIRED`, no member/initial-email leakage.
`POST /api/v1/admin/logout` body `{}` → 204, revokes session, expires cookie; clear
staff draft storage and cached detail. A naturally expired session retains drafts
for reauthentication as specified below. Public shells `/admin/*` other than
`/admin/login` and `/admin/invite` return 303 to login if signed out; signed-in
Viewer gets a 403 page for management routes. All protected APIs still enforce
roles independently of that navigation.

### Team endpoints (Admin only)

Member shape:
`{"id":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","email":"admin@example.test","role":"admin","active":true,"googleBound":true,"version":1,"joinedAt":"2026-10-17T14:30:00Z"}`.
Invitation shape:
`{"id":"45591203-0149-4b9b-a9dc-d728d9d83456","email":"staff@example.test","role":"viewer","state":"pending","expiresAt":"2026-10-18T15:00:00Z","version":1,"createdAt":"2026-10-17T15:00:00Z"}`.
Invite states: `pending`, `accepted`, `expired`, `revoked`; computed expiry is
authoritative even if periodic cleanup has not run. Token is 32 random bytes,
hash stored, expiration 24h, bound to normalized exact email and intended role.

| Endpoint | Request example | Success example / rules |
|---|---|---|
| `GET /api/v1/admin/team/members` | No body; `?limit=25&cursor=...` | 200 common list of Member objects; includes inactive memberships for audit. |
| `GET /api/v1/admin/team/invitations` | No body; optional `state=pending` and cursor | 200 common list of Invitation objects; never includes token/hash. |
| `POST /api/v1/admin/team/invitations` | `{"email":"staff@example.test","role":"viewer"}` + idempotency | 201 `{"data":{"invitation":{"id":"45591203-0149-4b9b-a9dc-d728d9d83456","email":"staff@example.test","role":"viewer","state":"pending","expiresAt":"2026-10-18T15:00:00Z","version":1,"createdAt":"2026-10-17T15:00:00Z"},"inviteUrl":"https://repair.example.test/admin/invite#token=example-invite","deliveryState":"preview_only"}}`; invalidates previous pending invites for same email transactionally; active member → 409 `MEMBER_EXISTS`. |
| `DELETE /api/v1/admin/team/invitations/{id}` | `{"expectedVersion":1}` | 204; revokes pending invite, cancels unsent invite mail. Expired/revoked same version is no-op; accepted cannot be revoked. |
| `PATCH /api/v1/admin/team/members/{id}` | `{"expectedVersion":1,"role":"viewer"}` | 200 `{"data":{"id":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","role":"viewer","active":true,"version":2}}`; invalidate all that member's sessions. |
| `DELETE /api/v1/admin/team/members/{id}` | `{"expectedVersion":2}` | 204; soft-deactivate, revoke sessions and pending invites; audit preserved. |

Role edit/removal counts **active Google-bound Admins** in the same
`BEGIN IMMEDIATE` transaction; operation that leaves zero → 409 `LAST_ADMIN`.
An unaccepted Admin invite does not count. Concurrent removal/demotion cannot
remove the last Admin. Self-removal/demotion is allowed only with another bound
Admin; response immediately signs the caller out. Subsequent role is re-read,
never trusted from an old token. Reinviting inactive membership requires a fresh
email-bound invite and verified sub policy; do not silently reset a different sub.

`POST /api/v1/auth/invitations/inspect` with anonymous CSRF,
`{"token":"example-invite"}` → 200
`{"data":{"state":"pending","role":"viewer","expiresAt":"2026-10-18T15:00:00Z","message":"Sign in with the Google account this invitation was sent to."}}`.
Do not disclose invitee email to an anonymous caller. Unknown/used/revoked/expired
all 410 `INVITE_UNAVAILABLE`. `/admin/invite#token=...` removes the fragment and
passes token to Google start; acceptance happens only in callback. Wrong verified
Google account is refused, invite remains pending, no unauthorized session issued.
Idempotent callback/acceptance transaction prevents two users redeeming one invite.
Invite emails obey the same demo policy as all outbound mail; a suppressed invite
still has an Admin-only copyable link, and no send-success claim.

## Staff request inbox, detail, offers and notes

Admin **and Viewer** may use this section. Status enum/customer labels are:

| Status | Label | Requirements / effect |
|---|---|---|
| `new` | Received | Public request default. |
| `reviewing` | Being reviewed | No response buttons. |
| `estimate_sent` | Estimate ready | Only via new estimate offer with valid amount/range/scope. |
| `needs_visit` | Please bring it in | Only via new visit offer with explanation; no amount. |
| `not_repairable` | We can't repair this | Nonempty `customerMessage`; no response buttons. |
| `awaiting_dropoff` | Waiting for drop-off | Customer accept or staff action; no appointment implied. |
| `in_shop` | In the shop | Item received; store `dropoffLocation`; work still Bel Air. |
| `in_progress` | Being repaired | No date promise. |
| `ready` | Ready for pickup | Explicit valid pickup location; email plus manual text action. |
| `picked_up` | Picked up | Set closedAt; cancel any unanswered offer. |
| `cancelled` | Closed | Set closedAt; cancel any unanswered offer. |

Backward changes and closed-ticket reopening require a staff-only `reason` of
10–500 characters, are audited, and clear closedAt on reopening. A change to any
status other than the offer's response state supersedes its unanswered offer.
Statuses are words, never decorative numbered steps. Patching to the same status
with no changed fields is a no-op (does not enqueue another email or increment).
`not_repairable` is a branch from the repair flow: entering it requires the public
explanation, while leaving it for an active status requires a staff-only reason.
Moving from that assessment to `cancelled` simply closes the request.

`GET /api/v1/admin/requests?filter=new&location=bel_air&q=boot&limit=25&cursor=...`
→ 200 common list of RequestSummary objects:

```json
{"data":{"items":[{"id":"358edbd1-060e-4559-9f2e-989c95c8f939","reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP","source":"online","status":"new","version":1,"itemType":"boots","customerName":"Example Customer","dropoffLocation":"bel_air","neededBy":null,"createdAt":"2026-10-17T14:30:00Z","updatedAt":"2026-10-17T14:30:00Z","photoCount":1,"delivery":{"failed":0,"uncertain":0,"pending":2,"previewOnly":0},"responsePending":false}],"nextCursor":null}}
```

Filter map: `new` = new/reviewing; `waiting` = estimate_sent/needs_visit/awaiting_dropoff;
`in_shop` = in_shop/in_progress; `ready` = ready; `closed` = picked_up/cancelled;
`all` = all including not_repairable. Optional explicit `status=not_repairable`
may be combined only with `filter=all`. Default `new`; all lists sort new status
first then createdAt descending, ID descending. `q` max 100; a complete reference uses exact normalized HMAC lookup, while other
queries use escaped parameterized substring search over staff-authorized
name/email/normalized phone, minimum two characters. Partial references are not
searched because references are stored encrypted; phone formatting is normalized.
No public search equivalent.
Empty result is `items:[]`, not 404; retain filters during navigation/back.

`GET /api/v1/admin/requests/{id}` → 200 RequestDetail:

```json
{
  "data": {
    "id":"358edbd1-060e-4559-9f2e-989c95c8f939",
    "reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP",
    "source":"online", "status":"new", "version":1,
    "itemType":"boots", "workTypes":["soles_heels"],
    "description":"The heel has separated from the sole of my left boot.",
    "brandAge":null, "neededBy":null,
    "contact":{"name":"Example Customer","email":"customer@example.test","phone":"+12025550123","preferred":"text","callbackPhone":null},
    "dropoffLocation":"dundalk", "pickupLocation":"dundalk", "repairLocation":"bel_air",
    "customerMessage":null, "offer":null,
    "photos":[{"photoId":"8666e050-c22b-4674-b82b-ae00cb853911","state":"ready","mediaType":"image/jpeg","width":1600,"height":1200,"bytes":184320,"url":"/api/v1/admin/requests/358edbd1-060e-4559-9f2e-989c95c8f939/photos/8666e050-c22b-4674-b82b-ae00cb853911"}],
    "createdAt":"2026-10-17T14:30:00Z", "updatedAt":"2026-10-17T14:30:00Z", "closedAt":null,
    "delivery":{"failed":0,"uncertain":0,"pending":2,"previewOnly":0},
    "demoMode":true,
    "links":{"events":"/api/v1/admin/requests/358edbd1-060e-4559-9f2e-989c95c8f939/events","notes":"/api/v1/admin/requests/358edbd1-060e-4559-9f2e-989c95c8f939/notes","offers":"/api/v1/admin/requests/358edbd1-060e-4559-9f2e-989c95c8f939/offers"}
  }
}
```

`offer` when present has the public Offer fields plus `version`, `state` (active,
answered, superseded), `createdBy` member ID and `customerMessage`; no private note
is ever placed into its scope/message implicitly. `response` is null or
`{"id":"9c253e41-8190-4483-bb67-45d70f3f7d03","choice":"request_call","recordedAt":"2026-10-17T15:10:00Z"}`.
Only detail has contact PII. Staff shared-link endpoint is separate to avoid loading
customer bearer tokens into every inbox response.
In request/offer mutation responses, `version` always means the resulting **request
version**; `offer.version` belongs to the offer record. Use request version as
expectedVersion on the next request mutation. Reading paginated child collections
does not advance it.

| Endpoint | Request example | Response example / semantics |
|---|---|---|
| `PATCH /api/v1/admin/requests/{id}` | `{"expectedVersion":3,"status":"ready","pickupLocation":"bel_air","customerMessage":"Your item is ready to collect.","reason":null}` | 200 `{"data":{"id":"358edbd1-060e-4559-9f2e-989c95c8f939","status":"ready","version":4,"updatedAt":"2026-10-17T16:00:00Z","notificationEventIds":["5e717985-8ca6-4ced-bda5-fcf3fdf67457"]}}`; fields other than expectedVersion may be omitted to preserve current values. No contact editing in this patch. |
| `POST /api/v1/admin/requests/{id}/offers` | `{"expectedVersion":1,"kind":"estimate","amountMinCents":1234,"amountMaxCents":2345,"scope":"Example sole repair after inspection.","timingNote":null,"customerMessage":"Please review this estimate."}` | 201 `{"data":{"offerId":"66c62863-dfe6-479d-b012-d991dd9df088","kind":"estimate","status":"estimate_sent","version":2,"sentAt":"2026-10-17T15:00:00Z","notificationEventIds":["5e717985-8ca6-4ced-bda5-fcf3fdf67457"]}}`. |
| `POST /api/v1/admin/requests/{id}/offers` | `{"expectedVersion":2,"kind":"visit","amountMinCents":null,"amountMaxCents":null,"scope":"Please bring the item in so we can examine the sole.","timingNote":null,"customerMessage":null}` | 201 same create-offer shape, `kind:"visit"`, `status:"needs_visit"`, request version incremented. |
| `GET /api/v1/admin/requests/{id}/offers` | No body; cursor/limit | 200 common list of Offer objects, newest first, including superseded offers and response. |
| `POST /api/v1/admin/requests/{id}/notes` | `{"expectedVersion":4,"text":"Customer will call about a Dundalk visit."}` | 201 `{"data":{"id":"7f68ad96-ddb2-4348-8d3d-7c16aedcb66e","text":"Customer will call about a Dundalk visit.","authorId":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","createdAt":"2026-10-17T16:02:00Z","requestVersion":5}}`; internal only. |
| `GET /api/v1/admin/requests/{id}/notes` | No body; cursor/limit | 200 common list of Note objects (same id/text/authorId/createdAt as above, no requestVersion), newest first. |
| `GET /api/v1/admin/requests/{id}/events` | No body; cursor/limit | 200 common list: `{"id":"a6e7138f-8861-4a62-b020-bb0f2a2ebfe9","type":"status_changed","fromStatus":"in_progress","status":"ready","message":"Your item is ready to collect.","visibility":"customer","actorId":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","reason":null,"at":"2026-10-17T16:00:00Z"}`; newest first, includes internal audit events without secrets. |
| `GET /api/v1/admin/requests/{id}/photos/{photoId}` | No body, session cookie | 200 binary JPEG with no-store, nosniff, sanitized `Content-Disposition: inline; filename="repair-photo.jpg"`; verify photo belongs to request and is ready, staff role every call. Missing/expired file → 404 `PHOTO_UNAVAILABLE`; UI retains metadata and shows unavailable state. No static `/uploads` mount or bearer/photo URL. |
| `POST /api/v1/admin/requests/{id}/share-link` | `{"channel":"print"}` or `{"channel":"text"}` + CSRF | 200 ShareLink below; no network send, record audit access. |

Offer validation: estimate minimum integer **1–100,000,000** cents (technical
bound, not pricing); maximum null for a single amount, or integer >= minimum and
<=100,000,000. Currency fixed USD. Scope required 10–2000; timingNote null or
1–300, optional message max 2000. Visit amount fields must be null. Closed requests
must first be explicitly reopened; cannot create an offer on a closed request.
An offer that would move backward (including leaving `not_repairable`) returns
409 `INVALID_TRANSITION`: first PATCH to `reviewing` with a staff-only reason,
then publish the offer at the resulting version. Offers accept no `reason` field.
Every offer is immutable; creating a replacement supersedes the previous active
offer and creates a new response opportunity. No editing an already sent amount
without an audit trail/new offer. `sentAt` means offer published to status/outbox,
not proof that Gmail delivered it. The disclaimer is appended server-side.

ShareLink example (staff-only):

```json
{"data":{"reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP","statusUrl":"https://repair.example.test/repair-status#token=bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM","channel":"text","smsHref":"sms:+12025550123?body=Your%20Clarke%27s%20repair%20status%3A%20https%3A%2F%2Frepair.example.test%2Frepair-status%23token%3DbW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM","message":"Your Clarke's repair status: https://repair.example.test/repair-status#token=bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM","deliveryState":"manual"}}
```

Text uses callback phone only for a requested callback action, otherwise ticket
contact phone; no phone → 422 field error. Encode SMS body safely for the mobile
platform; UI may adapt `?body=` versus `&body=` without changing recipient/content.
For `channel:print`, `smsHref:null`, `deliveryState:"print"`; render a printable
slip with reference/status URL and sourced location route. In demo, non-allowlisted
customer phone returns `smsHref:null`, `deliveryState:"preview_only"`; show
admin-only preview and do not create an actionable outbound destination. Public
business tel/sms links remain the verified business routes, never rewritten to a
test phone. Staff email/call/text customer actions are similarly suppressed in
demo unless their exact destination is configured in the respective allowlist.
Frontend obtains those allowed actions via `GET /api/v1/admin/requests/{id}/contact-actions`
→ 200 `{"data":{"callHref":null,"smsHref":null,"emailHref":null,"blockedByDemo":true}}`
for a non-allowlisted demo contact. For an eligible synthetic contact an example is
`{"data":{"callHref":"tel:+12025550123","smsHref":"sms:+12025550123","emailHref":"mailto:customer@example.test","blockedByDemo":false}}`.
Missing contact methods are null; do not reconstruct suppressed links from detail
PII. Status-bearing SMS still uses share-link. Share-link on an expired closed
request returns 404 `STATUS_UNAVAILABLE`; it does not renew the token implicitly.

### Walk-in tickets

`POST /api/v1/admin/requests` with CSRF/idempotency:

```json
{"itemType":"shoes","workTypes":["heel_tips"],"description":"Replace worn heel tips after assessment.","brandAge":null,"neededBy":null,"location":"bel_air","contact":{"name":"Example Walk-in","email":null,"phone":"+12025550123","preferred":"text"},"internalNote":null}
```

201 `{"data":{"id":"358edbd1-060e-4559-9f2e-989c95c8f939","reference":"CLK-7Q4M2-X9K6V-W3D8F-R5T2N-H9C6ZP","status":"in_shop","version":1,"source":"walk_in","createdAt":"2026-10-17T14:30:00Z","statusUrl":"https://repair.example.test/repair-status#token=bW9ja190b2tlbl9mb3JfY29udHJhY3Rfb25seV8xMjM"}}`.
No photo or draft required. Same field validation, contact minimum as resolved
above, pickup initially equals dropoff. Walk-in is recorded receipt of an item,
not an estimate approval or repair commitment. No-email ticket skips customer email
with a staff delivery indication; share-link/print works. Intake pause affects only
public new requests, not staff tickets or existing status operations.

### Concurrency and staff draft recovery

Every request mutation (including note/offer/response) increments one monotonic
request `version` after `UPDATE ... WHERE id=? AND version=?`. All checks, event,
outbox and audit inserts share one SQLite transaction. No merge of conflicting
business text. Conflict response, after authorization:

```json
{"error":{"code":"VERSION_CONFLICT","message":"Updated by someone else. Reload the latest details; your draft is kept.","fields":{},"retryable":false,"requestId":"c7d06238-730c-45cf-8d7a-f47283633d98","details":{"expectedVersion":4,"currentVersion":5,"resourceUrl":"/api/v1/admin/requests/358edbd1-060e-4559-9f2e-989c95c8f939"}}}
```

Same pattern for settings, hours, notices, team and outbox (their own version).
Frontend stores staff edit text, baseVersion, action idempotency key and resource
ID in sessionStorage keyed by **member ID**, TTL 12h. On 409, fetch latest alongside
the untouched draft and require deliberate reapply; never auto-increment the
expectedVersion and overwrite. On 401, retain draft, reauthenticate, verify same
member, refetch version and show differences. Different Google member must not
see the previous member's draft; purge it. Explicit logout clears all staff drafts.
Notes and queued send forms preserve text across refresh/back. Clear only the
successfully committed form; request/detail data itself is not persisted offline.

## Admin settings, hours and notices

Admin-only pages: `/admin/settings`, `/admin/locations`, `/admin/notices`.
No endpoint edits credentials, callback URL, demo allowlists or DEMO_MODE through
the browser. Fixed factual location addresses/phones/Maps links are code/KB-owned,
not arbitrary unverified owner HTML. Settings and hours have independent versions.

`GET /api/v1/admin/settings` → 200:

```json
{"data":{"version":1,"intakeAccepting":true,"intakePauseMessage":null,"notificationEmails":["alerts@example.test"],"emailDeliveryEnabled":false,"responseExpectation":null,"photoRetentionDays":180,"closedLinkDays":90,"pendingRetention":null,"demoMode":true,"testDestinationPolicy":{"emailAllowlistConfigured":true,"phoneAllowlistConfigured":true},"updatedAt":"2026-10-17T14:30:00Z"}}
```

`PATCH /api/v1/admin/settings`, request:

```json
{"expectedVersion":1,"intakeAccepting":false,"intakePauseMessage":"Please call or text to discuss your repair.","notificationEmails":["alerts@example.test"],"emailDeliveryEnabled":false,"responseExpectation":null,"photoRetentionDays":180,"closedLinkDays":90}
```

200 `{"data":{"version":2,"updatedAt":"2026-10-17T16:00:00Z"}}`; fetch full
settings after save. Fields optional except expectedVersion; no null-as-delete for
arrays/booleans. Notification emails: unique 0–5 (empty disables staff alerts with an Admin warning), normalized email validation;
non-allowlisted demo recipients are saved but explicitly preview-only. No private
allowlist values in the API. Pausing needs nonempty 1–280 message; unpaused message
may be null. `responseExpectation` staff-only max 300. Photo days integer 1–730,
link days 1–365, defaults 180/90; shortening requires additional
`confirmRetentionReduction:true`, and response includes
`retentionEffectiveAt` = now + 24h. Extension applies immediately. Worker uses
effective policy; staff preview must show impact before confirming. Audit changes.
`POST /api/v1/admin/settings/retention-preview` with CSRF and
`{"photoRetentionDays":90,"closedLinkDays":60}` → 200
`{"data":{"photosEligibleForDeletion":0,"linksBecomingUnavailable":0,"effectiveAt":"2026-10-18T16:00:00Z","confirmationRequired":true}}`.
Counts are evaluated against current state and may change before save. No mutation
or idempotency key is needed. GET settings additionally returns
`pendingRetention:null` or the pending days/effectiveAt object while a reduction is
scheduled; the active numeric values remain effective until then. Replacing a
pending reduction requires the current settings version and a fresh confirmation.
Omitting both retention fields preserves any scheduled change. Explicitly sending
the current active periods cancels a scheduled change; the UI distinguishes keep,
replace, and cancel and refreshes the active/pending policy after saving.
Missing required confirmation returns 422 on `confirmRetentionReduction`.
Enabling delivery with no connected sender → 409 `SENDER_DISCONNECTED`. On later
sender failure settings remain enabled but UI warns; requests continue saving.

`GET /api/v1/admin/hours` → 200:

```json
{"data":{"version":1,"timezone":"America/New_York","location":"bel_air","days":[null,null,{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"10:00","close":"13:00"}],"updatedAt":"2026-10-17T14:30:00Z"}}
```

`PUT /api/v1/admin/hours`, full replacement:
`{"expectedVersion":1,"days":[null,null,{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"09:00","close":"17:00"},{"open":"10:00","close":"13:00"}]}`
→ 200 `{"data":{"version":2,"updatedAt":"2026-10-17T16:00:00Z"}}`.
Days indexed Sunday=0 through Saturday=6; exactly seven entries; null = closed.
One interval/day; strict HH:mm, 00:00–23:59, closing strictly after opening,
no overnight range. Both null and all-closed week are valid. Timezone/location
cannot be changed; there is no Dundalk hours setter. Delete hours by setting days
closed, not removing the required singleton. `GET` returns current rule for editor.

Notice shape and full create example (Admin):

```json
{"locations":["bel_air"],"message":"Closed for a weather disruption.","reopenText":"Please call before visiting.","startsAt":"2026-11-03T09:00:00-05:00","endsAt":"2026-11-04T09:00:00-05:00"}
```

`POST /api/v1/admin/notices` + idempotency → 201:

```json
{"data":{"id":"c890e3f6-f68b-4532-b345-9670274d1a77","version":1,"locations":["bel_air"],"message":"Closed for a weather disruption.","reopenText":"Please call before visiting.","startsAt":"2026-11-03T14:00:00Z","endsAt":"2026-11-04T14:00:00Z","state":"scheduled","createdAt":"2026-10-17T14:30:00Z","updatedAt":"2026-10-17T14:30:00Z"}}
```

| Endpoint | Request | Response |
|---|---|---|
| `GET /api/v1/admin/notices?state=active&location=bel_air` | No body; optional `state=scheduled\|active\|expired\|all`, cursor/limit | 200 common Notice list, newest first, empty array valid. |
| `GET /api/v1/admin/notices/{id}` | No body | 200 full Notice above. |
| `PATCH /api/v1/admin/notices/{id}` | `{"expectedVersion":1,"message":"Closed today for weather.","endsAt":"2026-11-04T10:00:00-05:00"}` | 200 full updated Notice, version 2; omitted fields unchanged. |
| `DELETE /api/v1/admin/notices/{id}` | `{"expectedVersion":2}` | 204; soft-delete and audit; immediately disappears from public evaluation. |
| `POST /api/v1/admin/notices/preview` | Same fields as create, no idempotency required | 200 `{"data":{"locationIds":["bel_air"],"banner":{"message":"Closed for a weather disruption.","reopenText":"Please call before visiting."},"startsAt":"2026-11-03T14:00:00Z","endsAt":"2026-11-04T14:00:00Z","replacesActiveNoticeIds":[]}}`; validation only, no persisted change. |

Locations nonempty unique subset of bel_air/dundalk; both = both entries. Message
1–280 plain text, reopenText null or 1–160. Start/end must be explicit-offset
RFC3339 instants consistent with the local New York date/time; end > start.
Past starts allowed for immediate current notice; past ends allowed for correction
but render expired. No appointment availability is inferred from any notice text.

### Timezone, closures and stale-data behavior

Use `zoneinfo.ZoneInfo("America/New_York")` with installed tzdata, not UTC-offset
arithmetic. Normal hours use local weekday/date each time. Open interval is
`[open,close)`. `closing_soon` applies when 0 < remaining <=30m. Otherwise state is
`open`, `closed`, `closed_notice`, `unknown`; Dundalk is always `appointment_only`,
even with its activeNotice shown. No scheduled-notice leak before start.

Notices are closure intervals `[startsAt,endsAt)`. Per location choose the active
notice with latest `updatedAt`, then ID as deterministic tie-break; edits count as
newest. Only that banner shows, while availability calculation excludes the union
of **all** overlapping closure intervals (an older active closure must not create
a false opening when a newer one ends). Expiry hides automatically at read time.
Freeform reopenText is display-only; it never creates hours. Next opening is the
first future instant inside normal opening hours and outside all closure ranges;
if a notice ends mid-opening, that instant is next opening. Search up to 366 local
days; beyond that/all-closed/missing rules → nextOpensAt null, “Call before visiting”.
Never fabricate an opening when dependency/storage evaluation failed.

Editor uses local datetime controls plus timezone label. On a fall-back ambiguous
time it must ask for first/second occurrence (explicit -04:00/-05:00); spring-forward
nonexistent time → 422 `INVALID_LOCAL_TIME`. For rare regular hours falling in a
DST gap/fold, suppress that day's ambiguous interval as `unknown` with call fallback
until corrected, rather than guess. Usual business hours do not cross the switch.
NeededBy compares New York dates, not rolling 72-hour intervals. Token retention
uses exact elapsed UTC days, not local midnight.

Public `/locations` reevaluates against server clock; validUntil is earliest of
60s or next opening/closing/closing-soon/notice boundary. UI refreshes at expiry
and when tab becomes visible. Once stale or on 503/network failure, show “Call
before visiting”, both contact routes and static sourced addresses; do not keep a
stale green “Open” badge. DB failure → 503 `HOURS_UNAVAILABLE`; missing/corrupt
individual hours can return 200 state unknown for that location. Closure snapshot
is added to new-request confirmation and ready status with current location data.

## Gmail connection, outbox and audit

Pages `/admin/emails`, `/admin/emails/outbox/{id}`, `/admin/audit` are Admin-only.
Viewer request detail receives aggregate delivery badges, never unrelated email
recipients/bodies or sender management. A Gmail connection is separate from Google
staff login; signing out does not disconnect the sender. Same existing OAuth client
and `/oauth/callback`, purpose-bound state, `openid email gmail.send` scopes and
offline access. No Gmail read, mailbox search, Calendar or Drive permission.

`GET /api/v1/admin/email/connection` → 200:

```json
{"data":{"version":1,"state":"disconnected","senderEmail":null,"connectedAt":null,"deliveryEnabled":false,"demoMode":true,"lastSuccessAt":null,"lastError":null,"requiresReconnect":false,"queue":{"pending":0,"retryWait":0,"failed":0,"uncertain":0,"previewOnly":0}}}
```

Connection states `disconnected`, `connected`, `reconnect_required`, `degraded`.
When connected, senderEmail is visible only here and authorized audit records;
tokens/client secret/key paths never are. `lastError` null or sanitized
`{"code":"GOOGLE_REAUTH_REQUIRED","message":"Reconnect the Gmail sender."}`.

| Endpoint | Request example | Success / failure contract |
|---|---|---|
| `POST /api/v1/admin/email/connect` | `{"expectedVersion":1,"returnTo":"/admin/emails"}` + CSRF | 200 authorizationUrl/expiresAt envelope as Google start, bound to current Admin ID/version and connection version; callback 303 `/admin/emails?connection=connected`. If connection changed while OAuth was open, refuse overwrite with a sanitized conflict result. |
| `POST /api/v1/admin/email/test` | `{"recipient":"tester@example.test"}` + idempotency | 202 `{"data":{"outboxId":"5e717985-8ca6-4ced-bda5-fcf3fdf67457","status":"pending"}}`; disconnected →409; non-allowlisted demo recipient →403 `DEMO_DESTINATION_BLOCKED`, no queued send. This explicit Admin action may send an allowlisted test while general delivery is disabled. |
| `POST /api/v1/admin/email/disconnect` | `{"expectedVersion":2}` + idempotency | 200 `{"data":{"version":3,"state":"disconnected","deliveryEnabled":false,"providerRevocation":"pending"}}`; remove local encrypted tokens immediately, increment sender generation, disable delivery, cancel unsent rows; separately revoke old token at Google with bounded retries, no credentials in response. |
| `GET /api/v1/admin/outbox?status=failed&requestId=358edbd1-060e-4559-9f2e-989c95c8f939` | No body; status optional, cursor/limit | 200 common list of OutboxSummary objects below, newest first. |
| `GET /api/v1/admin/outbox/{id}` | No body | 200 OutboxDetail below. |
| `POST /api/v1/admin/outbox/{id}/retry` | `{"expectedVersion":3,"acknowledgePossibleDuplicate":false}` + idempotency | 202 `{"data":{"id":"5e717985-8ca6-4ced-bda5-fcf3fdf67457","status":"pending","version":4,"attemptCount":1,"nextAttemptAt":"2026-10-17T16:00:00Z"}}`; requires connected sender, delivery enabled and send policy still eligible. |
| `GET /api/v1/admin/audit?requestId=358edbd1-060e-4559-9f2e-989c95c8f939` | No body; optional actorId/action/cursor/limit | 200 common list: `{"id":"a6e7138f-8861-4a62-b020-bb0f2a2ebfe9","at":"2026-10-17T16:00:00Z","actorId":"d7ef1622-021d-4941-bcc8-ce2a1cc19547","action":"request.status_changed","entityType":"request","entityId":"358edbd1-060e-4559-9f2e-989c95c8f939","fromVersion":3,"toVersion":4,"summary":"Status changed from in_progress to ready."}`. |

OutboxSummary, complete example:

```json
{"id":"5e717985-8ca6-4ced-bda5-fcf3fdf67457","requestId":"358edbd1-060e-4559-9f2e-989c95c8f939","kind":"customer_ready","recipient":"customer@example.test","subject":"Your Clarke's repair is ready for pickup","status":"failed","version":3,"attemptCount":1,"createdAt":"2026-10-17T15:00:00Z","nextAttemptAt":null,"sentAt":null,"lastError":{"code":"SENDER_DISCONNECTED","message":"Connect the Gmail sender, then retry."},"canRetry":false,"retryNeedsDuplicateAcknowledgement":false}
```

OutboxDetail is that same object **plus**:

```json
{"bodyText":"Your item is ready for pickup at Bel Air. View your repair status using your private link.","bodyHtml":"<p>Your item is ready for pickup at Bel Air.</p>","policyReason":null,"attempts":[{"number":1,"startedAt":"2026-10-17T15:00:02Z","finishedAt":"2026-10-17T15:00:02Z","result":"failed","errorCode":"SENDER_DISCONNECTED","providerMessageId":null}],"lastRetriedBy":null,"bodyPurged":false}
```

Preview markup is server-generated escaped text with fixed templates, never
customer HTML. Render in sandboxed iframe with no scripts, forms, external resources
or top navigation; native text alternative available. Links in mail must use the
configured origin/verified location routes. Do not log body or private status URLs.
Audit view contains safe actions/IDs/version changes; internal text, contact PII,
OAuth tokens and image contents are not duplicated into general audit logs.
`canRetry` reflects both row state and current connection/policy; when false the
error/policy reason explains the prerequisite. After body retention expires,
`bodyText` and `bodyHtml` are null, `bodyPurged:true`, and retry remains disabled.
Before purge OutboxDetail includes `bodyPurged:false`.

### Notification events and delivery guarantees

| Trigger in committed transaction | Recipients/content |
|---|---|
| Online request created | `customer_received` to customer; `staff_new_request` individually to configured notification emails. Reference, item/work summary, next action, both contact routes; staff alert links to authenticated detail/photos, never attachments/public photo URLs. |
| Walk-in ticket created | Customer receipt if email exists; staff new-ticket alert. No-email recorded as skipped in request event, no fake recipient/outbox send. |
| Estimate offer created | `customer_estimate` with amount/range, scope, disclaimer, optional staff timing note, status link. |
| Visit offer created | `customer_needs_visit` with explanation and correct dropoff route, no invented amount/appointment. |
| Status changed to not_repairable | `customer_not_repairable` with required public explanation and call route. |
| Status changed to ready, or pickup location changed while ready | `customer_ready` with pickup location/hours/appointment route and active closure notice. Manual text action available; no automatic SMS. |
| Customer accept/decline/request_call | `staff_customer_response` to notification emails; callback number staff-only. Status reflects response immediately; no extra unsolicited customer email. |
| Invite created | `team_invite` to exact invited email, expiring link; demo rules apply. |
| Explicit connection test | `connection_test` to selected allowed test email; isolated from request lifecycle. |

No email for every internal note, history read, ordinary progress patch, location
notice edit, pickup/closure or idle poll. Re-entering a notification status is a new
audited event and can create new mail; replaying the same action cannot. A stale
unsent offer/ready message is marked cancelled/superseded when a newer contradictory
event commits; the worker rechecks that relation before delivery. Staff alert
destinations are snapshotted at event creation, normalized/deduplicated, one row
per recipient, never public To/CC lists. Missing alert configuration is an Admin
warning and does not reject a customer request.

`outbox.event_key` unique = event UUID + kind + normalized recipient hash. All
domain changes, notification rows and audit commit together. Render previews
whether sending is allowed or not. A failed outbox insert rolls back the domain
mutation; a subsequent **delivery failure does not**. On success page say request
received, never email delivered. Neither a `sent` Gmail API response nor a test API
call alone proves inbox receipt; live acceptance requires actual receipt evidence.

Outbox state machine:

- `preview_only`: demo recipient not allowlisted or delivery disabled; persisted
  preview, no network send. `policyReason` is `demo_recipient_blocked` or
  `delivery_disabled`. Never automatically promote historical previews when mode,
  allowlist or sender changes. Create a new explicit eligible event if needed.
- `pending` → worker atomically leases row → `sending`. One worker at a time;
  claim with SQLite compare-and-swap, lease 120s, unique lease token. Network call
  outside DB transaction; finalize only with that lease and sender generation.
- `sent`: provider success + provider message ID, immutable terminal result.
- `retry_wait`: failure known to have happened **before acceptance**; nextAttemptAt
  and safe code stored. Initial attempt plus at most 5 automatic retries with
  1m, 5m, 30m, 2h, 12h delays and 0–20% jitter, honoring longer Retry-After.
- `failed`: permanent validation/recipient error, disconnected/reauth-needed
  sender, or exhausted safe retries. Visible badge and manual retry path.
- `uncertain`: process died in `sending`, connection/read timeout after send began,
  or ambiguous 5xx after request body transmission. **No automatic resend**.
  Admin can retry only with `acknowledgePossibleDuplicate:true`; the UI explains
  possible duplicate mail and records that explicit decision.
- `cancelled`: revoked invite, superseded offer/status notification or disconnected
  sender; no automatic send/retry. Sent/preview_only/cancelled/sending rows return
  409 `EMAIL_NOT_RETRYABLE` on retry.

Token refresh/connect timeout is safely retryable before message submission.
Google `invalid_grant`/revocation → reconnect_required; send 401 → refresh once,
then fail safely if rejected. Explicit 429/rate-limit rejection → retry_wait;
other 4xx → failed. Never resend merely because a timeout elapsed. Gmail does not
provide a promised exactly-once send through this contract; deterministic
Message-ID is diagnostic, not deduplication. This conservative retry policy builds
on the [Gmail error guidance](https://developers.google.com/workspace/gmail/api/guides/handle-errors)
while retaining Oasis's uncertain-send safeguard. Each attempt is auditable.

Connection replacement/disconnection takes the send mutex, stops new claims,
waits at most 25s for an in-flight request, then invalidates sender generation.
A send already accepted by Google cannot be recalled; mark unresolved attempt
uncertain and report it in audit. Revocation job stores old token encrypted only
until success or 24h bounded expiry, then removes it and retains sanitized outcome.
Do not hold a SQLite write lock while waiting for a network operation.

### Demo isolation and integration configuration

Keep test identities in root-only runtime.env/private recovery only:
`DEMO_ALLOWED_EMAILS` (comma-separated exact normalized addresses),
`DEMO_ALLOWED_PHONES` (exact E.164), `NOTIFICATION_EMAILS` (initial settings seed).
Empty/missing allowlist means **no external destination permitted**. No wildcard,
domain-wide match, alias folding, “same sender” exception or runtime browser editor.
Existing `INITIAL_ADMIN_EMAIL`/`OPERATOR_EMAIL` do not automatically allow outbound
mail; add the approved identity privately when the implementation is tested.

Check allowlist both on enqueue and immediately before send; suppress if policy
changed. Apply to customer/staff/invite/test messages, generated customer `mailto:`,
call and SMS actions; never auto-redirect customer content to a test inbox.
Public business contact/Maps/social navigation is the actual verified destination,
not application-generated notifications. Status pages and confirmation remain free
of demo labels; admin labels and outbox policy reasons explain suppression.
All environment databases, uploads, keys, sender tokens, OAuth clients and queues
remain independent. Never copy production contact data into previews or reuse
another site's token. `.env` files or test accounts never enter source/dist/image.

## Persistence, migrations and invariants

DB: `/data/clarke.sqlite3`. Per-connection `foreign_keys=ON`, `busy_timeout=5000`;
WAL journal, `synchronous=FULL`. One connection per request/job; close promptly.
Use bound SQL parameters, allowlisted sort/columns, `BEGIN IMMEDIATE` for writes.
On busy exhaustion roll back and return 503 `DATABASE_BUSY`, Retry-After 2–5s;
client keeps drafts/key. No catch-and-return-success fallback. SQLite is the only
arbiter for concurrent write/last-admin/idempotency/photo ownership decisions.
Random UUIDv4 primary IDs, UTC integer milliseconds internally, RFC3339 on wire.
JSON columns use `CHECK(json_valid(...))`; enum/check constraints match this file.

Tables (required columns; `created_at`/`updated_at` UTC and integer `version` on
mutable entities; no unlisted public projection follows from an internal column):

| Table | Required data and constraints |
|---|---|
| `schema_migrations` | integer version PK, checksum, applied_at; reject changed already-applied migration. |
| `app_meta` | key PK/value; schema/app compatibility, bootstrap_provisioned, environment identity. Never customer/sender credentials here. |
| `settings` | singleton id=1, version, validated JSON values, pending retention policy/effective_at, timestamps. |
| `hours` | singleton location=bel_air PK, version, timezone=America/New_York, seven-day JSON, updated_at. |
| `members` | id PK, email_norm UNIQUE, google_sub UNIQUE nullable until bound, role admin/viewer, active, version, bound_at/joined_at/updated_at. Inactive members preserved for audit. |
| `sessions` | sid_hash PK, csrf_hash, member_id nullable FK, member_version nullable, created_at, last_seen_at, absolute_expires_at, idle_expires_at, revoked_at, auth_method (anonymous/google); session ID never stored raw. |
| `invitations` | id PK, token_hash UNIQUE, encrypted_token for one-time response/email retention, email_norm, role, creator_id FK, expires_at, accepted_at/by FK, revoked_at, version. Unique pending invite/email enforced transactionally (expiry reconciled first). |
| `oauth_states` | state_hash PK, sid_hash FK, purpose login/gmail, encrypted verifier/nonce payload, initiating member/version, invite_hash, connection_version, return_to, expires_at, consumed_at. |
| `drafts` | id PK, token_hash UNIQUE, created_at, expires_at, state active/submitted/deleted, request_id FK nullable, receipt_cipher nullable; no form PII stored pre-submit. |
| `requests` | id PK, reference_hash UNIQUE, reference_cipher, status_token_hash UNIQUE, status_token_cipher, source online/walk_in, data_mode demo/operational, is_synthetic default false, version, status, item_type, work_types JSON, description, brand_age nullable, needed_by nullable, contact_name/email_norm/phone_e164/preferred, callback_phone nullable, dropoff_location, pickup_location, repair_location=bel_air, customer_message nullable, current_offer_id nullable FK, created_at/updated_at/closed_at, consent_version/accepted_at nullable for staff walk-in. |
| `photos` | id PK, draft_id FK, request_id nullable FK, state, slot 0–4, raw/sanitized relative storage IDs, source_sha256, output_sha256, bytes, width/height, media_type, error_code, created_at/ready_at/attached_at/deleted_at, processing_lease/expires_at. Unique live slot/draft partial index; no user-supplied paths/filenames. |
| `offers` | id PK, request_id FK, kind estimate/visit, state active/answered/superseded, USD, min/max cents nullable only as specified, scope, timing_note/customer_message nullable, created_by FK, created_at, version. One active unanswered offer/request partial unique index. Immutable content. |
| `customer_responses` | id PK, request_id FK, offer_id FK UNIQUE, choice enum, callback_phone nullable, created_at. Exactly one answer per offer; cannot replace. |
| `request_events` | id PK, request_id FK, type, from_status nullable, status, public_message nullable, visibility customer/internal, actor_id nullable FK, reason nullable, related_offer_id nullable FK, request_version, created_at. Append-only. |
| `notes` | id PK, request_id FK, author_id FK, text, created_at, request_version. Append-only, never public. |
| `notices` | id PK, version, location flags, message/reopen_text, starts_at, ends_at, created_by/updated_by FK, created_at/updated_at/deleted_at. CHECK end > start. |
| `integration_secrets` | name PK (gmail), Fernet ciphertext containing sender email/sub and tokens, version/sender_generation, state, connected_at, last_success_at, sanitized last_error. No plaintext OAuth tokens. |
| `revocations` | id PK, encrypted token, due_at, expires_at, attempt_count, sanitized outcome; only used for disconnect cleanup. |
| `outbox` | id PK, event_key UNIQUE, event_id, request_id/offer_id/invite_id nullable FK, kind, recipient_norm, subject, body_cipher (HTML/text incl. bearer link), policy_reason, status, version, sender_generation, attempt_count, created_at/next_attempt_at/sent_at, lease_token/lease_expires_at, last_error_code, provider_message_id nullable. |
| `outbox_attempts` | id PK, outbox_id FK, attempt_number, started_at/finished_at, result, error_code, provider_message_id nullable, retry_actor_id nullable, duplicate_ack boolean; UNIQUE(outbox_id,attempt_number). |
| `audit_events` | id PK, actor_id nullable FK, action, entity_type/id, from/to_version, safe summary, created_at. Append-only, minimal data; not raw request bodies. |
| `idempotency` | actor_scope_hash + route + key_hash composite PK, canonical_payload_hash, encrypted_response/status, entity_id, created_at, expires_at, tombstone flag. Session rotation must preserve member/draft scope, not bind solely to ephemeral sid. |
| `rate_limits` | bucket_key HMAC PK, token balance/counter, refill_at, expires_at; atomic consumption. |
| `file_deletions` | id PK, photo_id nullable FK, exact relative storage key UNIQUE, queued_at, attempts, completed_at; retryable unlink queue. |

Required indexes beyond PK/UNIQUE: requests `(status,created_at DESC,id)`,
`(dropoff_location,status,created_at DESC,id)`, `(closed_at)` partial where closed,
normalized contact email/phone and name search key (substring query may scan bounded
staff results; no FTS requirement initially); photos `(request_id,state)` and
`(state,created_at)`; offers/events/notes `(request_id,created_at,id)`;
notices `(starts_at,ends_at,deleted_at,updated_at)`; sessions/invites/oauth/drafts
expiry indexes; outbox `(status,next_attempt_at,created_at)` and `(request_id,created_at)`;
attempts `(outbox_id,attempt_number)`; audit `(entity_type,entity_id,created_at)`;
idempotency/limits expiry; file_deletions `(completed_at,queued_at)`.

DB enforces closed statuses with nonnull closed_at, others null; status/location
enums; visit amounts null; estimate min positive/max>=min; valid photo states and
owner associations. Domain service verifies current_offer belongs to request,
response offer/request match, roles, date rules and legal transition prerequisites.
Unique constraints are final guards against races, not just prior SELECT checks.

### Migration and filesystem transaction sequence

Versioned forward-only migrations under `app/migrations/`:

- `001_core.sql`: schema/migration/meta, members/sessions/invites/OAuth, settings,
  hours/notices, request/draft/photo/offer/response/event/note tables and indexes.
- `002_delivery.sql`: integration secrets, outbox/attempts/revocations, audit,
  idempotency, rate limits, deletion queue and indexes.
- `003_defaults.py`: insert only sourced location/hours defaults, empty operational
  settings, private initial-admin seed and bootstrap marker. No prices, sample
  repair tickets, photos, sender account or public test identity. Migrations do
  not run a network call or mutate an existing bound membership.

On startup acquire single migration lock, verify migration checksums and existing
DB schema, apply each transaction before readiness. Existing placeholder fixture
tables, if any, are inspected/left intact unless a separately authorized migration
identifies their ownership; never drop an unknown table. Initial settings:
intake accepting, delivery disabled, notification emails from private config (empty
allowed at first boot with Admin warning), retention 180/90. A missing config should
not prevent credential-free candidate health, but login/send readiness stays false.

Preserve `/data/secret.key` and `/data/encryption.key`, matching the provisioned
`SESSION_SECRET`/`ENCRYPTION_KEY`. Read existing Oasis-compatible bytes; do not
generate replacements when a mounted key exists. Mismatched env/file values or
unreadable encryption data fail readiness with a sanitized error, never overwrite.
Generate random local keys only on fresh credential-free isolated data volumes;
persist mode 0600 with parent dir 0700. Encryption key must be valid Fernet bytes.
Customer contact data is DB-private (not public encryption claims); bearer secrets,
Gmail tokens and outbox bodies are application-encrypted. Backups still contain
keys and require root-only protection.

SQL and filesystem cannot share an atomic commit. Use staged fsync/rename, then
DB `ready` state; request commit only claims already durable files. On rollback
they remain draft-owned. For deletion, mark inaccessible and queue exact storage
keys in the same DB transaction, then unlink outside it. Startup reconciliation
removes unreferenced expired staged files, retries pending deletions, and records
missing attached files as unavailable rather than fabricating a photo. Never follow
symlinks or storage keys outside `/data/uploads`; use generated names/open-no-follow.

Keep migrations backward-compatible for a rolling candidate check where practical;
image rollback alone cannot undo schema changes. Existing updater quiesces and
snapshots complete `/data`, keys and matched config before replacement; restore
the matched set on migration failure. Test DB integrity and representative image
reads after restore; never restore one environment's snapshot into another.
Restore preflight uses the installed target's fixed environment/origin, image
package and paths, plus its current trusted Compose policy. It validates archive
runtime/release/DB identity before stopping the service or changing target state;
the final HTTPS check uses the target's pinned origin. Older revisions of the same
package remain restorable with matching environment and Compose policy. A changed
Compose policy is rejected before mutation and needs operator reconciliation.

### Retention and operational cleanup

Demo defaults: unsubmitted drafts/accepted unclaimed photos 24h, interrupted raw
upload leases 5min, raw decoded input deleted immediately, attached sanitized photos
180 elapsed days after close. Reopening before logical photo deletion cancels pending
retention; deleted photos do not magically reappear. Closed status access expires
90 elapsed days; retain only staff detail thereafter. Retention reductions are
delayed 24h as above. Contact details and request/offer/event/note records remain
with the request (no automatic contact purge invented by this contract); owner must
approve actual contact retention at handover.

Expire sessions on deadline, purge expired/revoked sessions after 24h; delete OAuth
payload within 1h of consumption/expiry; purge unused invite token ciphertext at
expiry/acceptance, preserve minimal membership/invite audit 1y. Idempotency full
responses 7d with durable creation tombstones; rate-limit keys expire after their
window +24h. Outbox body ciphertext expires 90d after sent/preview/cancelled/failed
terminal status (failed/uncertain rows then become nonretryable with body omitted
and `bodyPurged:true`); retain safe delivery metadata/audit 1y. Uncertain mail stays
visible for review during that window. Keep active request records separate from
short-lived session/queue maintenance.

Deletion is idempotent and audited. Backup copies can retain data past logical
deletion; existing host backup retention/off-server policy remains an owner-dependent
operational gap, not silently changed here. A restored backup must run current
retention/deletion reconciliation before reopening public access. No global Docker
prune or app-volume deletion is part of this work. Synthetic acceptance records
are marked privately with exact IDs then purged by an audited **operator CLI**
(not public DELETE) including dependent photos/outbox/contact fields; it refuses
unmarked/non-synthetic records. This CLI must not live in the runtime HTTP surface.

## Runtime and test contract

`GET /health` → 200 `{"status":"ok"}` only when migrations/config/key consistency
and local SQLite connectivity are healthy; 503 `{"status":"unavailable"}` otherwise.
Google/Gmail outage does not make the application unhealthy or lose intake.
`GET /version.json` → 200 `{"revision":"<full-build-git-sha>"}`, no-store, matching
image/source labels and release checks. No environment secrets, SQL schema or
stack traces in health/version. Network-isolated updater candidate with empty
synthetic state and no credentials remains healthy and has no outbound worker send.

Frontend routes served by Flask's explicit shell allowlist, including direct reload:
`/`, `/repair-request`, `/repair-request/complete`, `/repair-status`, `/admin/login`,
`/admin/invite`, `/admin/requests`, `/admin/requests/new`, `/admin/requests/{uuid}`,
`/admin/settings`, `/admin/locations`, `/admin/notices`, `/admin/team`, `/admin/emails`,
`/admin/emails/outbox/{uuid}`, `/admin/audit`. Additional sourced brand-page routes
may be added by frontend owner. Unknown `/api`, `/oauth`, `/uploads`, traversal and
unknown asset paths return actual 404, never SPA HTML. Unknown extensionless
page navigations accepting HTML get the dedicated missing-page HTML with recovery
links and HTTP 404; API/private-file errors remain JSON. Frontend routes imply no
unimplemented backend endpoints. Assets served only from dist; no `/data` path.

Security headers: CSP self-only default/script/connect/font/style/media/image
(local blob images for draft previews explicitly allowed), `object-src 'none'`,
`base-uri 'self'`, `frame-ancestors 'none'`, restrictive form-action plus Google as
needed. Outbox iframe uses sandboxed srcdoc. OAuth callbacks load no external page
resources. `X-Robots-Tag: noindex,nofollow` on admin/status/request receipts always,
and all preview/demo pages; retain current sitewide noindex until release approval.
No logging body, Authorization, Cookie, query OAuth codes, email destination or
status fragment; request IDs/action IDs and safe error codes suffice.
Application and gateway access logs must omit query strings (staff search can
contain contact data) and use route templates instead of credential-bearing input.
The frontend does not put staff search contact values into page URLs or analytics.

### Signed-session e2e fixtures without a deployed bypass

Existing `scripts/app.py` creates a uniquely named candidate Compose project,
ephemeral host port (`APP_PORT=0`), network and `/data` volume, then passes
`BASE_URL=http://candidate:8080` to Docker target `e2e`. The launcher mounts
**only that exact candidate's synthetic named volume** into the fixture image,
after checking the container and volume Compose ownership labels, UID, read-only
filesystem and memory/PID limits. No installed
or live data volume, root runtime.env, real OAuth token, host Docker socket or
application login secret is provided to the test container.

The e2e image includes `tests/e2e/seed_sessions.py`, Python runtime auth serializer
and Playwright. After candidate schema readiness, the fixture opens the shared
synthetic SQLite DB directly, inserts test members/sessions with synthetic Google
subjects, sets auth_method=google using the ordinary session schema, hashes sid
and CSRF, and signs the sid with the **candidate-generated** `secret.key` through
the same serializer as production. It adds the cookie to Playwright and obtains
the matching CSRF normally; no HTTP login/seed endpoint or special runtime header.
This is controlled fixture construction, **not evidence of actual Google login**.
Seed Admin/Viewer/expired/uninvited cases separately, use example.test data, and
keep fixture IDs tagged is_synthetic. Fixture writes use SQLite transactions, not
live DB file replacement. Never seed demo instances on application startup.

Fixture code exists **only** in the `e2e` Docker target and its build context;
exclude it, test packages, fixture keys/accounts, test-clock controls, mock Gmail
adapter and browser binaries from `runtime`. `.dockerignore` admits only
`tests/e2e` beneath root `tests/`; explicit COPY puts test sources into test/e2e,
never into runtime. A build check
inspects the runtime image for fixture paths/routes/env/header bypasses. Negative
tests enumerate **every** admin API/asset with no cookie and expired/revoked/wrong
role sessions; all must reject. Public login shell and OAuth callback are the
documented exceptions, not privileged admin APIs.

Local start has no fixture shortcut. Staff fixture browsing happens inside the
isolated e2e candidate/browser context or via its test-only session export to the
test browser, never by changing an existing environment's cookie/data. Production
OAuth clients are not modified to add localhost callbacks. Real Google/Gmail checks
use their already configured independent HTTPS environments in the later authorized
live test stage; contract work does not sign in, connect, send or deploy.

Run `python scripts/app.py check` / `./app.ps1 check`; it must run backend unit/API
tests in Docker target `test`, exact-image health/revision, then `e2e` at desktop
1440 and phone 375 widths. E2e's exit status gates check/CI. Candidate test origin is
explicitly `http://candidate:8080`; cookies may be non-Secure only on that isolated
HTTP candidate. No published fixed e2e port; use discovered ephemeral port only
for read-only local inspection. All temporary candidate containers/networks/volumes,
test images and nonshared disposable build cache are removed by exact identity
after result capture, preserving designated local app environments/tool homes.

`check --keep-candidate` retains a successful isolated candidate for the local
integration walkthrough, switches its configured origin to its discovered loopback
port and exports synthetic Admin/Viewer signed cookies into gitignored `.runtime/`.
Those cookies come from the e2e-only direct-DB fixture; no runtime seed or login
shortcut exists. Remove that exact candidate afterward with `clean-candidate`.
The e2e candidate permits only the reserved fictional phone +1-202-555-0123 for
manual SMS-link assertions; email allowlists remain empty, so no email is sent.

Decoder implementation detail: libheif uses pthreads for tiled HEIC even with
decoder workers disabled. The seccomp policy permits only thread-form `clone`
(`CLONE_THREAD`), makes `clone3` unavailable and denies fork/vfork/exec, file opens,
network sockets and process-memory access. Threads inherit the same filter and
descriptor-only access. Each conversion checks file, socket and fork denial.

Unit tests inject a clock into time functions for DST/gap/fold cases; runtime does
not read a public test-clock header. Dependency failure tests use a fake transport
only in test images or test process injection, never a configurable deployed Gmail
endpoint. E2e previews are generated without network mail. Safe retries/uncertain
state, SQLite busy, interrupted image processing and restore tests need targeted
integration tests; passing a unit fixture alone does not prove live delivery.

### Acceptance coverage obligations (not completed by this document)

| Area | Required implementation evidence |
|---|---|
| RR-FORM/PHOTO/LOC/CONF/PAUSE | Both locations, 0/3/5 photos, sixth/type/size failures, real HEIC EXIF stripping, partial conversion and expiry, per-file progress, retained drafts/offline/back/deep links, paused-in-transaction race, timing warning, closed confirmation, duplicate-key and duplicate-draft races, honeypot/rate-limit and Gmail failure without lost intake. |
| RS-EST/RESP/TRACK/WALKIN/READY | Amount/range/visit/not-repairable, accept/decline/callback once per offer, new offer supersession, wrong token/reference/email/phone-last4 indistinguishability and throttling, 90-day expiry/reopen, no public PII/photo/internal-note exposure, phone-only walk-in, manual demo-safe SMS/print, ready pickup location/closure. |
| AD-AUTH/INBOX/TICKET/SET/TEAM/OUTBOX | All unauthenticated/Viewer-denied paths, initial email/sub binding, wrong/expired/used invites, concurrent last-admin removals, search/filter empty states, 409 retains typed text, 401 re-sign-in preserves same-member drafts, Gmail connect/disconnect/error/allowlist, safe retry versus uncertain acknowledgement, no deployed fixtures. |
| LN-HOURS/NOTICE/LOC | Tue–Sat boundaries and Saturday short hours, 30-minute close warning, DST and offset validation, all-closed/unknown fallback, notices per-location/scheduled/overlap/newest/expiry, editor validation, no Dundalk open/fixed-hour state, correct sourced link destinations. |
| Cross-cutting | 375px card containment/enlarged text/focus/word-only trackers, desktop/mobile hands-on recordings, no console errors, realistic phone/API performance, isolation, replacement persistence, complete SQLite/uploads/keys/config restore, checks against final source revision. |

Parent retains the feature matrix; no row is promoted to pass on the strength of
this contract. The 13 later live rows require synthetic flows and actual Google
sign-in/allowlisted inbox receipt separately on derek-dev, abdul-dev and production,
plus active backup timers and cleanup. Google clients/protected infrastructure are
already provisioned; actual app authentication, decoding memory fit, mail delivery,
owner policy approval and off-server recovery remain unverified until those stages.
