# Features

Build type: **functional**. Spec written 2026-10-17 by the spec stage (Claude Opus 5.5 high)
from the full research KB. Nothing here is an owner decision: no contact with the business
was made. Facts cite [sources](sources.md); everything marked **demo default** is our
working assumption, shown to the owner for approval before `DEMO_MODE=false`.

## Selected features

| ID | Feature | Class | Why it earns its place |
|---|---|---|---|
| `repair-request` | Photo repair request | build | Every repair is assessed per item, and the business advertises detailed estimates [S2][S3][S5]. Today's forms ask only for name/email/phone/city or a free subject/message, with no item, damage, photo or location field, and the contact form shows a broken `[recaptcha]` string [S1][S4]. Customers' real questions (can this be fixed, what will it cost, where do I go) need item context and photos [S5][S14][S19]. |
| `repair-status` | Estimate reply and repair status | build | The owner letter stresses avoiding communication breakdowns [S6]; reviews value honest assessment, including being told when something can't be repaired [S12]. A request with a status link gives the shop one place to reply with an estimate (or "bring it in so we can look") and later mark it ready, without a phone-tag loop. Covers walk-in tickets so in-shop drop-offs get the same lookup. |
| `staff-admin` | Staff admin (Google sign-in, Admin/Viewer) | build | Needed to run the two features above and the notices below. Oasis pattern, unchanged. |
| `location-notices` | Locations, hours and closure notices | build (small) | Two locations with different visit rules: Bel Air is the main repair shop with regular hours, behind Main St. via Burns Alley; Dundalk is appointment-only by call/text, and all repair work happens in Bel Air [S1][S4][S14][S15]. Closures happen (January 2026 storm closure, holiday posts) and are announced only on social media [S16][S18]. Stale phones and hours persist across the old site and directories [S1][S12][S13]. An owner-editable source of truth fixes that. |

Runner-ups for the owner conversation (not built):
- **Dundalk appointment slots** with real availability: only if Clarke's wants online booking and shares appointment windows and a calendar. Today the phone/text process is the system; we keep it.
- **Automatic SMS** (pickup ready, estimate sent) through a provider such as Twilio: needs an owner account and opt-in wording. The build uses staff-sent prefilled texts instead.
- **Post-pickup review request** email linking their Google Maps profile.
- **Key duplication / specialty inquiry** routing (keys, boat covers, satin dyeing are single-source or historical [S3][S5][S20]).
- **Mail-in repairs** and **online payment or deposits**: no evidence of either [S10][S11][S12]; would need shipping, pricing and payment policies first.

Not built, by evidence: payments (no working shop or checkout; directories list cash/check or cash only [S10][S11][S12][S13]); public prices (the `/pricing/` values are placeholder-like and must never be shown, quoted, seeded publicly or used as defaults [S11]); same-day, while-you-wait or 24-hour promises [S3][S11]; Messenger (single-source link, response untested [S1]).

## Existing systems we integrate with (instead of rebuilding)

| ID | System | Class | Use | Check |
|---|---|---|---|---|
| `call-text` | Phones: Bel Air 410-836-8316 (`tel:`), Dundalk 443-386-3800 (`tel:` and `sms:`) [S1][S4][S14][S15] | integrate | Primary action everywhere; Dundalk appointments stay call/text. Never link the legacy 410-284-2458 [S1][S13]. | Links open the dialer/SMS with the right number on phone. |
| `maps-directions` | Google Maps listings for both locations [S14][S15] | integrate | Directions links; Bel Air copy keeps "(REAR)", Burns Alley and the pharmacy/restaurant landmarks [S1][S16]. | Each link opens the matching listing. |
| `social-links` | Facebook `clarkesexpressshoerepair`, Instagram `clarke_the_shoe_doc` [S1][S16][S17] | integrate | Footer links. | Each opens the profile. |
| `gmail-sender` | Google account connected as sender (Oasis Admin → Emails) | integrate | Staff alerts and customer emails. Derek's Gmail in demo; owner's at handover. | Test email arrives. |

No booking, POS, ticketing or payment system was found in public sources [S1][S4][S10][S11]; this does not rule out a private one (owner question). The WordPress Contact Form 7 forms are replaced, not integrated.

## Shared rules (all features)

- **Time zone** `America/New_York` for every date, hour and "open now" check, including DST changes.
- **Bel Air hours, demo default:** Tue–Fri 9:00–17:00, Sat 10:00–13:00, Sun/Mon closed, from the current homepage and Maps agreement [S1][S14]. Older Tue/Thu/Fri 9–6 text conflicts [S12]; hours are admin-editable and need owner confirmation.
- **Dundalk:** no fixed hours anywhere in the product. It is always "by appointment, call or text 443-386-3800" [S1][S4][S15]. The site never shows Dundalk as "open".
- **Repairs happen in Bel Air** [S1][S4]. Copy must not imply Dundalk does work on site.
- **Prices:** no prices anywhere public. Estimates are typed by staff per request; there is no price list, calculator or default amount. Preview seed data uses obviously fake test amounts visible only in the admin and test status pages.
- **No promises the KB doesn't support:** no turnaround guarantee, no same-day, no 24/7, no warranty terms, no medical claims for orthopedic work [S3][S5][S11]. Copy says "estimate", "we'll review", "after we see it in person".
- **Request ≠ appointment ≠ estimate.** Every confirmation says which of these the customer has, in plain words.
- **Demo mode** (`DEMO_MODE=true` in every environment until the owner approves): outbound email goes only to allowlisted test addresses (Derek's, Abdul's); anything else is rendered to the admin outbox preview and not sent. Demo labels appear only inside the admin, never on public pages.
- **Abuse limits:** honeypot field, per-IP and per-contact rate limits, idempotency key per submission, server-side validation of every field. No reCAPTCHA by default (the current one is visibly broken [S4]); Turnstile can sit behind a flag if spam appears.
- **Privacy:** photos and contact details are visible only to signed-in staff. Photos are re-encoded server-side with metadata (including GPS) stripped. Demo default retention: photos deleted 180 days after a request is closed; contact data kept with the request record. Owner confirms or changes (handover checklist).
- **Design constraints** from X Solutions' saved design preferences and the [design brief](design-brief.md): no step numbering in forms or the status tracker (use words and position, not "1 / 2 / 3"); native inputs; controls checked against their cards at 375 px and with enlarged text; switching location or form views slides without a reload and keeps input; SVG icons only; admin uses the public visual language.

## Per feature: user stories, states, business rules

### `repair-request`: photo repair request

Scoped IDs: `RR-FORM` intake form, `RR-PHOTO` photo upload, `RR-LOC` location choice, `RR-CONF` confirmation and emails, `RR-PAUSE` intake pause.

**Customer stories**
- As someone with worn boots, I describe the item and damage and add a few photos, so Clarke's can tell me whether it's repairable and roughly what it costs before I drive over.
- As a Dundalk-area customer, I can ask Clarke's to contact me to arrange a Dundalk appointment, and I'm told clearly that I don't have an appointment until they confirm by phone or text, or I can call or text right away.
- As someone with a deadline (an event), I can say when I need it, without being promised that date.

**Staff stories**
- As Farrell or Bryan, I get an email for each new request with the item, damage, photos link and the customer's preferred contact, so I can reply between jobs.
- As staff, I can pause online requests (vacation, backlog) and the form then shows call instructions instead.

**Fields** (all server-validated)
- Item type, required: shoes, boots, handbag or purse, belt or strap, leather jacket or garment, luggage, baseball glove, other leather item, keys (single-source service, routed as "ask us" [S3]). Values come from verified offerings [S2][S3][S20].
- What it needs, optional multi-select: soles or heels, heel tips, stretching or fit, orthopedic lift or modification, stitching, zipper, dye or color, clean and condition, straps or hardware, not sure. Must include "not sure".
- Description, required, 10–2000 characters.
- Brand or approximate age, optional, max 120.
- Photos, `RR-PHOTO`: 0–5 images, JPEG, PNG, WebP or HEIC, max 10 MB each, re-encoded to JPEG/WebP. Photos are encouraged, not required: a customer without photos can still submit.
- Location, `RR-LOC`, required: "Bel Air (main repair shop)" or "Dundalk (by appointment)". Choosing Dundalk reveals the call/text 443-386-3800 actions above the rest of the form and changes the submit label to "Send request and ask for a Dundalk appointment".
- Needed by, optional date: not in the past; within 3 days shows an inline note that timing is confirmed only after review.
- Name required; email required (for the status link); phone optional except required when preferred contact is call or text; preferred contact: email, call or text.
- Consent line (not a checkbox): photos and details are used only to answer this repair request.

**Business rules**
- A submission creates one request with a short reference (for example `CLK-7Q4M2`, unambiguous characters) and an unguessable status token. Double-submit or retry with the same idempotency key returns the same request.
- Upload happens before submit with per-photo progress; the request is created only when all accepted photos are stored. Partial uploads are cleaned up after 24 hours.
- On success: customer email (reference, summary, status link, what happens next, both locations' contact routes); staff alert email to the configured notification addresses.
- What-happens-next copy, demo default: "We'll look at your photos and reply with an estimate or ask to see it in person." No response-time promise unless the owner sets one in settings.
- If submitted when Bel Air is closed or a closure notice is active, the confirmation adds "We're closed right now; we'll review it when we reopen [next opening from hours and notices]."
- Dundalk requests never create a time slot. Staff arrange it by phone or text and record it as a note.

**Customer UI states:** empty form; filling (location switch slides, input kept); field validation error inline next to the field, input kept, focus moves to first error; photo uploading (per-file progress, can remove); photo rejected (wrong type, too big, over 5) with plain reason, other photos kept; HEIC converting; submitting (button disabled, spinner, no layout jump); success page; duplicate submit (same success page); rate-limited (plain message plus call/text numbers); server or network error (input and photos kept, retry button, call/text fallback); offline (message, retry when back); Bel Air closed now (note on success page); closure notice active (notice above form); intake paused by staff (form replaced by both locations' call/text actions, no dead form); session or page refresh mid-form (draft kept locally, photos re-attached or clearly asked again).

### `repair-status`: estimate reply and repair status

Scoped IDs: `RS-EST` estimate reply, `RS-RESP` customer response, `RS-TRACK` status page and lookup, `RS-WALKIN` walk-in ticket, `RS-READY` ready-for-pickup notice.

**Statuses** (customer label in quotes; staff can move forward or back, every change audited):
- `new` "Received": request submitted.
- `reviewing` "Being reviewed".
- `estimate_sent` "Estimate ready": staff entered an estimate.
- `needs_visit` "Please bring it in": photos aren't enough to quote.
- `not_repairable` "We can't repair this": with staff explanation (honest-assessment theme [S12]).
- `awaiting_dropoff` "Waiting for drop-off": customer accepted or was asked to bring it.
- `in_shop` "In the shop": item received (Bel Air or Dundalk drop-off).
- `in_progress` "Being repaired".
- `ready` "Ready for pickup": with pickup location.
- `picked_up` "Picked up" (closed).
- `cancelled` "Closed": customer declined or staff closed it.

**Customer stories**
- As a customer, I open my status link and see what Clarke's said: the estimate, what it covers, any note, and what to do next.
- I can answer an estimate: "I'll bring it in", "No thanks", or "Please call me". No payment is taken.
- When it's ready, I get an email (and, if I chose text, a text from the shop) telling me where to pick it up and that location's hours or appointment route.
- If I lost the link, I enter my reference plus my email or phone's last four digits.

**Staff stories**
- As staff, I write an estimate on the request: amount or range typed by me, what it covers, optional timing note, and optional message. It sends the customer email and updates the status page.
- As staff with a walk-in, I create a ticket in under a minute (name, contact, item, work, location) so the customer gets the same status link.
- As staff, I mark "ready" and choose the pickup location; the customer is notified. "Text customer" opens my phone's messaging app with a prefilled message to their number (no SMS provider).

**Business rules**
- Estimates: currency amount or range entered by staff, always labeled "estimate; final price confirmed when we see the item in person". No default amounts.
- Customer response is allowed only in `estimate_sent` or `needs_visit`, and only once per estimate; a new estimate reopens it. Accept moves to `awaiting_dropoff` and shows the drop-off route: Bel Air address with rear-entrance directions and hours, or Dundalk "call or text 443-386-3800 to set a time".
- Pickup location defaults to the drop-off location (**demo default**; owner confirms how Dundalk items return from Bel Air [S1][S4]).
- Status page shows current status in words with a simple progress line labeled by words, never numbers; history of customer-visible events; no internal notes.
- Lookup: reference plus email or phone last four; identical generic error for any mismatch; rate-limited. Status tokens don't expire while the request is open; demo default 90 days after closing they show "This request is closed, call us" instead of details.
- Emails sent on: request received, estimate sent, needs visit, not repairable, ready. Each email is logged in the outbox with status (sent, preview-only, failed, retried).
- Walk-in tickets don't require photos or email; without email the customer gets the reference on a printed or texted slip (staff "Text status link" prefilled message).

**Customer UI states:** status loading (skeleton, no blank flash); each status above with its own next-step copy; estimate awaiting response (three actions); response submitting; response recorded (with what happens next); response already recorded (read-only, call link); not repairable (explanation, no action buttons except call); ready (location card, hours or appointment route, active closure notice if any); closed/picked up; link not found or invalid (generic, lookup form, call links); lookup error (generic); lookup rate-limited; expired closed request; network error with retry.

### `staff-admin`: staff admin

Scoped IDs: `AD-AUTH` Google sign-in and roles, `AD-INBOX` request inbox and detail, `AD-TICKET` walk-in ticket, `AD-SET` settings, notification addresses and intake pause, `AD-TEAM` invites and removal, `AD-OUTBOX` email log.

**Access** (Oasis pattern, Astra owns): Google sign-in only, no password login, no deployed test bypass. `INITIAL_ADMIN_EMAIL` is Derek's Google account (kept in `runtime.env`, not here). Admins invite by email as Admin or Viewer with expiring, email-bound links; Admins can remove admins but not the last one. Viewers handle requests, estimates, statuses, tickets and notes; Admins also manage settings, hours, notices, team and the Gmail sender. Every admin route rejects requests without a real Google session (tested).

**Staff stories**
- As staff on a phone at the counter, I see new requests first, open one, zoom photos, write an estimate and move on.
- As an Admin, I set which addresses get new-request alerts (demo: Derek's test inbox; owner chooses among the four published inboxes or another [S1][S4][S16]).
- As an Admin, I can see whether each email went out and retry failed ones.

**Inbox and detail:** filters New, Waiting on customer, In shop, Ready, Closed, All; search by reference, name, email or phone; location filter. Detail shows item, work, description, needed-by, photos (authenticated full-size view), contact actions (call, text, email), status control, estimate composer, internal notes, history. Concurrent edits use a version check: the second save sees "Updated by someone else, reload" and keeps typed text.

**Staff UI states:** signed out; sign-in in progress; sign-in denied (not invited, plain message); invite accept; invite expired, used or wrong Google account; session expired mid-edit (re-sign-in keeps the draft); inbox loading; inbox empty ("No new requests"); filter with no results; detail loading; photo missing or still processing; estimate validation error (amount required for `estimate_sent`, explanation required for `not_repairable`); save conflict; email failed (badge on request, retry in outbox); Gmail sender disconnected (Admin warning, requests still saved); Viewer opening settings (hidden in nav, 403 page if forced); removing last admin blocked; demo-mode label (admin only); phone layout usable one-handed.

### `location-notices`: locations, hours and closure notices

Scoped IDs: `LN-HOURS` hours and open-now, `LN-NOTICE` closure notices, `LN-LOC` location cards.

**Customer stories**
- As a visitor, I see at a glance which location to use: Bel Air for walk-in repairs with today's hours and an open or closed state; Dundalk by appointment with call and text buttons.
- When the shop is closed for weather or a holiday, I see that before I drive over.
- I find the Bel Air rear entrance from the landmark directions.

**Staff stories**
- As an Admin, I post a notice ("Closed today for snow; reopening Wednesday 10am") for one or both locations with start and end times, and it disappears on its own.
- As an Admin, I correct regular hours without a developer.

**Business rules**
- Open-now for Bel Air only, from hours plus active closure notices, in `America/New_York`. Shows "Open until 5 pm", "Closed, opens Tuesday 9 am", or "Closed today" during a notice.
- Notices: location (Bel Air, Dundalk or both), message (max 280), optional reopen text, start and end; at most one active per location (newest wins); scheduled notices allowed; expired notices hidden automatically. Shown on home, location cards, request form and status pages for `ready` items.
- Hours seed is the demo default above. The legacy Dundalk number and old fixed Dundalk hours never appear [S1][S13].
- Location cards: address, landmark directions for Bel Air, public parking in front of the rear shop [S1], phone, directions link; Dundalk adds text button and appointment note.

**Customer UI states:** open now; closing soon (within 30 minutes); closed with next opening; closed today by notice; scheduled notice not yet active (hidden); notice active for Dundalk only; hours data missing or failed to load (falls back to "call before visiting" plus phone, never a wrong state); Saturday short hours; DST change day.

**Staff UI states:** hours editor with validation (close after open, per-day closed toggle); notice editor (preview of public banner, end after start); notice saved; notice expired list; Viewer read-only.

## API and infrastructure implications (for Astra; contract lives in `docs/API.md`)

- Stateful route: Oasis `server/` install, persistent `/data` (SQLite plus `/data/uploads`), root-only `runtime.env`, daily backup that includes uploads, tested restore, updater with data snapshot. Separate data, keys and OAuth client per environment; previews start empty.
- Reverse proxy and app body limit sized for 5 × 10 MB uploads; image re-encode and metadata strip in the container (HEIC needs libheif or equivalent); photos served only through an authenticated route.
- Data: requests, photos, status events, estimates, customer responses, notes, tickets (same table as requests with a source field), notices, hours, settings, admins, invites, sessions, email outbox, audit timestamps.
- Endpoints, indicative: public request create (idempotent), photo upload, status by token, status lookup, estimate response, public hours and notices; admin sign-in and session, inbox list and search, request detail and update with version, estimate create, ticket create, notices and hours CRUD, settings, team and invites, outbox list and retry.
- Notifications: Gmail sender only (Oasis). No SMS provider, no calendar, no payments.

## Operational checklist (what the owner must provide or approve)

Demo-complete is not operational. Each item is open until done.

| Item | Feature | Status |
|---|---|---|
| Confirm they want photo requests online and approve the confirmation and estimate wording | `repair-request`, `repair-status` | owner must approve |
| Choose the inbox that receives request alerts and who replies; optional response-time target | `repair-request` | owner must provide [S1][S4][S16] |
| Connect the owner's Gmail sender; real test email received | all | owner must provide |
| Owner's staff Google accounts invited as Admin or Viewer; owner admin accepted | `staff-admin` | owner must provide |
| Confirm Bel Air hours (current versus older 9–6 text) | `location-notices` | owner must confirm [S1][S12][S14] |
| Confirm Dundalk process: call/text only; who answers; how Dundalk items get back from Bel Air; pickup location rule | `repair-request`, `repair-status` | owner must confirm [S1][S4] |
| Confirm whether 410-284-2458 is retired or forwarded | `call-text` | owner must confirm [S1][S13] |
| Photo retention and closed-request link period (demo defaults 180 and 90 days); privacy wording | `repair-request`, `repair-status` | owner must approve |
| Item and service list in the form (keys, boat covers, satin dye, orthopedic work) | `repair-request` | owner must confirm [S3][S5][S20] |
| Who posts closure notices | `location-notices` | owner must decide |
| Payment methods text, if any is shown (none shown by default) | `location-notices` | owner must confirm [S12][S13] |
| Handover: disconnect Derek's Gmail sender; replace test notification addresses and phone; remove Derek as admin after owner accepts; repeat each live row with owner accounts | all | not started |
| Approve `DEMO_MODE=false` | all | not started |

## Template flow notes

To be filled at the template stage: REA notes of the chosen template's intake, upload and status flows (states, validations, transitions) to match.

## Acceptance

All rows are untested. Result stays `fail` until the scenario has actually been run and its evidence recorded.

| Phase | Feature | Scenario | Viewport | How tested | Result | Evidence |
|---|---|---|---|---|---|---|
| pre | repair-request | Happy path Bel Air: item, work, description, 3 photos, submit, success page with reference and status link, customer and staff emails in outbox | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Happy path Bel Air with photos from phone | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Dundalk choice reveals call/text 443-386-3800 first, submit label changes, confirmation says no appointment until Clarke's confirms; no time slot created | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Submit without photos succeeds | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Validation errors inline next to fields, input and photos kept, focus on first error | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Phone required only when call or text is preferred | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Wrong file type, over 10 MB and sixth photo rejected with plain reason, others kept | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | HEIC photo accepted and re-encoded; stored image has no GPS metadata | desktop | API test | fail | unverified: not yet tested |
| pre | repair-request | Needed-by in the past rejected; within 3 days shows timing note, no promise | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Double-click submit and retried request create one record | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Rate limit and honeypot block abuse; normal single submission unaffected | desktop | API test | fail | unverified: not yet tested |
| pre | repair-request | Submitted while Bel Air closed or notice active: confirmation names next opening (incl. DST weekend) | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Intake paused: form replaced by both locations' call/text actions | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Email sender down: request saved, customer sees success, outbox shows failed, retry sends | desktop | Playwright e2e with failing sender | fail | unverified: not yet tested |
| pre | repair-request | Server error or offline: message, input and photos kept, retry works, call/text fallback shown | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Refresh and back button mid-form keep draft; deep link to form works | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-request | Demo mode: email to non-allowlisted address is preview-only, not sent | desktop | API test | fail | unverified: not yet tested |
| pre | repair-request | Form controls fit their cards at 375 px, with 200% text and visible focus | 375 | Hands-on walkthrough | fail | unverified: not yet tested |
| pre | repair-status | Staff sends estimate; customer email rendered with amount, estimate wording and link; status page shows it | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Customer accepts estimate: status becomes waiting for drop-off with correct location route | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Customer declines and asks for a call: recorded once, second response blocked, staff sees it | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Needs visit and not repairable statuses show correct copy and actions | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Staff marks ready with pickup location: customer page and email update, closure notice shown if active | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Lookup by reference plus email or phone last four; mismatches give identical generic error; rate-limited | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Invalid token and closed-request expiry show generic page with lookup and call links | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Walk-in ticket without email or photos creates reference; "Text status link" opens prefilled sms link | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | repair-status | Status tracker uses words, no step numbers; internal notes never shown to customer | desktop | Hands-on walkthrough | fail | unverified: not yet tested |
| pre | staff-admin | Every admin route rejects requests without a real Google session; no bypass in deployed image | desktop | API test | fail | unverified: not yet tested |
| pre | staff-admin | Initial admin signs in; invites Viewer; invite bound to email, expires, wrong account refused | desktop | e2e with signed test session plus manual Google check | fail | unverified: not yet tested |
| pre | staff-admin | Viewer can update requests and estimates but not settings, hours, notices or team | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | staff-admin | Last admin cannot be removed | desktop | API test | fail | unverified: not yet tested |
| pre | staff-admin | Inbox filters, search and empty states; new requests first | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | staff-admin | Two staff edit one request: second save gets conflict message and keeps typed text | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | staff-admin | Session expires mid-estimate: re-sign-in keeps draft | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | staff-admin | Photos only reachable with staff session | desktop | API test | fail | unverified: not yet tested |
| pre | staff-admin | Admin usable one-handed on phone: open request, zoom photo, send estimate, mark ready | 375 | Hands-on walkthrough | fail | unverified: not yet tested |
| pre | location-notices | Bel Air open, closing soon, closed with next opening across Tue–Sat hours and DST change | desktop | Unit plus e2e with fixed clock | fail | unverified: not yet tested |
| pre | location-notices | Dundalk never shows open; always appointment with call and text 443-386-3800; legacy number absent site-wide | 375 | Playwright e2e plus page scan | fail | unverified: not yet tested |
| pre | location-notices | Admin posts closure notice for Bel Air: shows on home, card, form and ready status; expires on its own | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | location-notices | Hours data failure falls back to "call before visiting", never a wrong state | 375 | Playwright e2e | fail | unverified: not yet tested |
| pre | location-notices | Hours editor and notice editor validation | desktop | Playwright e2e | fail | unverified: not yet tested |
| pre | call-text, maps-directions, social-links | tel, sms, Maps and social links open the right destinations; no placeholder prices anywhere | 375 | xs-check required links plus page scan | fail | unverified: not yet tested |
| pre | all | Records and photos survive container replacement; backup restore including uploads tested once | n/a | Container replacement and restore drill | fail | unverified: not yet tested |
| pre | all | No console errors or failed requests; main pages fast on mid-range phone | 375 | Browser check | fail | unverified: not yet tested |
| pre | all | Hands-on customer and staff walkthrough with screen recording of each main flow | desktop and 375 | Hands-on walkthrough | fail | unverified: not yet tested |
| live | repair-request | derek-dev: synthetic request with photo; Derek's test inbox receives customer and staff email | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | repair-status | derek-dev: estimate sent, accepted, marked ready; customer page updates; test records removed | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | staff-admin | derek-dev: Derek signs in with Google; unauthenticated admin request rejected | desktop | Live check | fail | unverified: not yet tested |
| live | location-notices | derek-dev: notice posted and expired; open state correct for current time | desktop | Live check | fail | unverified: not yet tested |
| live | repair-request | abdul-dev: synthetic request with photo; test inbox receives emails | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | repair-status | abdul-dev: estimate to ready flow; test records removed | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | staff-admin | abdul-dev: Google sign-in works; unauthenticated admin request rejected | desktop | Live check | fail | unverified: not yet tested |
| live | location-notices | abdul-dev: notice and open state correct | desktop | Live check | fail | unverified: not yet tested |
| live | repair-request | production: synthetic request with photo; test inbox receives emails; record deleted after | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | repair-status | production: estimate to ready flow; test records deleted, production data clean | 375 | Live synthetic flow | fail | unverified: not yet tested |
| live | staff-admin | production: Derek signs in with Google; unauthenticated admin request rejected | desktop | Live check | fail | unverified: not yet tested |
| live | location-notices | production: open state correct; no notice left active | desktop | Live check | fail | unverified: not yet tested |
| live | all | Each environment: backup timer active; DEMO_MODE=true; previews noindex | n/a | Server check | fail | unverified: not yet tested |
