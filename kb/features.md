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

Observed 2026-10-17 in the T3 preview browser at 1440 and 375 px. No form was submitted
(not even an empty one), no account was created, nothing was added to a cart. REA could not
attach: its own Chrome launch failed ("provider is closing") and the loopback port 9222
answered without a DevTools listing, so DOM, attributes and visible states were read with
in-page inspection instead. Server-side validation, emails and status pages were therefore
not observed. Template choice and visual traits: [design brief](design-brief.md#template-site).

**Template intake: The Restory quote form** (`go.the-restory.com/request-a-quote`, embedded
in an iframe on `/us-en/exceptional-bag-restoration#form`).
- One white card (640 px at desktop) on a light-grey page, title "Tell us about your bag",
  required-field note under it. Three serif sub-headings inside the one card, each followed
  by a single helper sentence: describe the issue (textarea), upload photos (dropzone), then
  your details (name, email, address, social handle, two consent checkboxes). No wizard and
  no step numbers; the whole form scrolls as one document.
- Photos: dashed dropzone with "Drag & Drop Files Here / or / Browse Files"; JPEG and PNG
  only; attributes set minimum 1, maximum 5, while the copy says "up to 4". Helper text asks
  for exterior, interior and relevant details. A "0 of 5" counter sits in the corner.
- Form markup identifies Contact Form 7, a honeypot field and hCaptcha. Server-side and
  post-submission validation were not exercised; no inline error states were observed.
- Their advertised workflow describes an assessment from notes and images, then a quote
  by email, with order, shipping and completion emails on the paid route and an account
  "Orders" page. These post-submission states were not tested.
- 375 px: card goes full-bleed; every control is inset 15 px and none overflows.

**Adopted** for `repair-request` and `repair-status` (spec rules above still decide):
- Keep the one-card, sub-headed document: Your item (type, what it needs, description,
  brand or age), Photos, Where you'll bring it (location, needed by), How to reach you.
  Location switching slides within the card and keeps input (standing preference).
- Dropzone plus native file button, guided wording borrowed in spirit from Rago Brothers'
  optional photo assessment ("full item" and "close-up of the area that needs work"):
  photos encouraged, not required (spec), up to 5, limits stated in words before
  choosing files. Each file shows as a thumbnail chip with progress and a remove button.
  No "0 of 5" style counter; the limit message appears only when reached. Copy and the
  enforced limit always match (the template's 4-versus-5 mismatch is not repeated).
- Inline validation next to each field after submit or blur, focus on the first error, input
  and photos kept (spec); the template's validation behavior remains unverified.
- Quote reply becomes our estimate on a tokenized status page instead of an account; status
  is words on a progress line (spec), with email triggers defined by this site's spec.
- Not adopted: price calculator, cart, checkout, shipping address, social-handle field,
  newsletter consent, captcha (spec uses honeypot and rate limits).

**Runner-up evidence used**
- Rago Brothers guest mail-in form (`shop.ragobrothers.com/repairforms/new.htm`): name,
  email, phone with mobile/home type, shipping address, then an item table ("Item", with
  colour and brand guidance, plus "Repairs needed") with "add another item", terms
  checkbox. Contact assessment form: up to 4 optional photos, 25 MB combined, labelled
  "Photo of full item" and "Close-up photo of areas needing repair". A customer account
  and a separate retailer login (repair-ticket platform) exist; both gated.
- Leather Spa: repair wizard, estimates, status and payment are all behind sign-in.
- SoleHeeled: a Typeform price quiz with Stripe; did not advance in the preview.

**Staff admin:** no reference exposes staff screens. The admin uses the Oasis pattern with
the public type, colour and controls; nothing here is observed from a template.

## Acceptance

Reconciled 2026-10-17 under Derek's explicit Astra frontend/triage override: **45/45 pre pass; 13/13 live pass** within the final single-account scope. The user explicitly restricted live authentication to the existing Admin account and excluded separate-account Viewer acceptance. That excluded flow is not claimed as a live pass; local Viewer/invitation coverage remains pre-release evidence. All temporary invitations were withdrawn with no invitation mail or second member added.

Release evidence: reviewed correction `42235a04b629b5ee53669365dd48446d70f87f6e` passed hosted 138 backend/API and 83 browser cases; focused R8 review found no actionable issue. Original accepted `37fd564` remains historical. PR #2 released main `f8d72bd`; both previews inherit it. R9 real Chrome flows passed authentic Google login and same-member re-entry, Gmail connections and five actual inbox messages per environment, mobile photo intake, estimate/accept/ready, privacy, notice creation/automatic expiry and exact cleanup. All three remain demo/noindex. Private R9 receipts retain final revisions, branch isolation and scoped cleanup.

Evidence scope: the completed R4 run passed **134 backend/API + 81 browser cases**, including the 1440/375 contexts; the earlier combined run passed 121 + 44. The parent verified the 28-file R4 source manifest before committing `37fd564eb87aeffb6223d70b482c1662d483d57e`. The separate committed-candidate check exited 0 with the same 134 + 81 results; the parent affected-screen visual pass is accepted. Four additional backend/API cases and four targeted browser scenarios close the remaining functional evidence gaps without application changes. R4 includes explicit reduced-motion contexts, portrait fit/actual-size and print-media/generated-PDF assertions, not a human PDF review or physical print. The 19 accepted review/walkthrough findings are fixed; no prior backend objection remains open.

Test-source keys (each identifier below names an actual completed test): **F** = [browser flows](../tests/e2e/test_flows.py), **M** = [browser management](../tests/e2e/test_management.py), **R** = [R4 browser regressions](../tests/e2e/test_review_r4.py), **A** = [API](../app/tests/test_api.py), **S** = [security](../app/tests/test_security.py), **U** = [uploads](../app/tests/test_uploads.py), **H** = [hours](../app/tests/test_hours.py), **E** = [edge cases](../app/tests/test_edges.py), **L** = [mail](../app/tests/test_mail.py), **P** = [pagination](../app/tests/test_pagination.py), **N** = [R4 backend regressions](../app/tests/test_review_r4.py). **V1** denotes the parent's completed portions of the 2026-10-17 walkthrough (1440/820/375), including customer and staff recordings; unfinished or superseded visual checks are not passes. Private run reports `triage-fixes-r4.md`, `review-r2.md`, `visual-r1.md`, `backend-r1.md`, `backend-r2.md` and the bounded `acceptance-map-r5.md` retain execution provenance and limitations outside this public repository.

Phase correction: the XS functional acceptance gate puts real-provider acceptance **after deployment**, separately from pre-release tests, to avoid a circular build gate. Pre 29 therefore uses ordinary signed synthetic sessions and process-local Google protocol/invitation tests. Pre 34 still requires draft preservation through expiry and same-member local re-entry; merely retaining storage is insufficient. Actual Google sign-in/re-sign-in remains mandatory in the existing live staff-auth row for **each of all three environments**; the separate-account live Viewer invite/account-binding portion was later explicitly excluded by the user's single-account restriction. Actual Gmail/inbox receipt remains mandatory in each live intake row. No included live requirement is marked pass by a mock provider, local session fixture, preview-only mail, or local retry-to-sent test. The excluded Viewer portion remains unexercised live.

| Phase | Feature | Scenario | Viewport | How tested | Result | Evidence |
|---|---|---|---|---|---|---|
| pre | repair-request | Happy path Bel Air: item, work, description, 3 photos, submit, success page with reference and status link, customer and staff emails in outbox | desktop | Real-container browser intake, receipt reload/back and authenticated outbox/photo reads; preview-only mail | pass | R4: F.test_bel_air_three_photos_receipt_emails_refresh_back checks three attached photos, receipt/reference and the two notification kinds. V1 exercised receipt-to-status navigation. |
| pre | repair-request | Happy path Bel Air with photos from phone | 375 | Same actual intake test in the 375 px context | pass | R4: F.test_bel_air_three_photos_receipt_emails_refresh_back[phone]; V1 separately completed a recorded phone intake with three photos (Dundalk). |
| pre | repair-request | Dundalk choice reveals call/text 443-386-3800 first, submit label changes, confirmation says no appointment until Clarke's confirms; no time slot created | 375 | Browser location switch/submit and API receipt assertions, plus parent phone walkthrough | pass | F.test_dundalk_no_photos_and_location_switch_preserves_input; A.test_submission_idempotency_draft_pause_and_outbox; V1 inspected both contact routes and the no-appointment receipt. |
| pre | repair-request | Submit without photos succeeds | desktop | Browser zero-photo submission to real API | pass | F.test_dundalk_no_photos_and_location_switch_preserves_input and F.test_failed_delivery_fixture_keeps_request_and_explains_disconnected_sender both reach a saved receipt without attachments. |
| pre | repair-request | Validation errors inline next to fields, input and photos kept, focus on first error | 375 | Browser invalid submission with a retained photo plus parent empty-submit interaction | pass | F.test_validation_phone_date_focus_and_retained_photo checks invalid-field focus, retained description/photo and recovery; V1 empty submit focused location and showed inline errors. |
| pre | repair-request | Phone required only when call or text is preferred | desktop | Browser text-preference validation plus API validation of both call/text and successful phone-free email submission | pass | F.test_validation_phone_date_focus_and_retained_photo; A.test_public_validation_origin_csrf_privacy rejects missing phone for call and text, then accepts email preference without phone. |
| pre | repair-request | Wrong file type, over 10 MB and sixth photo rejected with plain reason, others kept | 375 | Browser rejection/recovery with genuine HEIC and API size/count/concurrency checks | pass | F.test_bad_oversize_sixth_photo_and_real_heic; U.test_type_size_count_partial_upload_and_expiry; U.test_sixth_slot_concurrency_and_replay. |
| pre | repair-request | HEIC photo accepted and re-encoded; stored image has no GPS metadata | desktop | Genuine 4032x3024 HEIC conversion, stored-image inspection and bounded decoder RSS; real HTTP drill | pass | U.test_real_12mp_heic_under_runtime_limit; F.test_bad_oversize_sixth_photo_and_real_heic. Backend R1: sanitized 2048x1536 JPEG, no EXIF/XMP/ICC/comment, sample peak RSS 117940 KiB; scripts/check_backend.py completed twice. |
| pre | repair-request | Needed-by in the past rejected; within 3 days shows timing note, no promise | desktop | Browser past-date rejection and same-day timing warning; New York date-boundary unit test | pass | F.test_validation_phone_date_focus_and_retained_photo asserts TIMING_NOT_CONFIRMED; E.test_new_york_needed_by_and_retention_reduction_activation. |
| pre | repair-request | Double-click submit and retried request create one record | desktop | Double-click actual UI and replay its captured payload/key/draft; inspect record, receipt, event and notification identities | pass | F.test_double_submit_one_record; A.test_duplicate_submit_race. Exactly one ticket/draft/received event and one customer-plus-staff notification set. |
| pre | repair-request | Rate limit and honeypot block abuse; normal single submission unaffected | desktop | Actual intake threshold tests with distinct drafts | pass | R6 app/tests/test_acceptance_r6.py: request-IP 10/hour, normalized email 3/hour and phone 3/hour; each rejects two further distinct drafts with 429 and unchanged record/event/outbox counts, then unrelated intake succeeds. Existing honeypot/normal test also passed. |
| pre | repair-request | Submitted while Bel Air closed or notice active: confirmation names next opening (incl. DST weekend) | desktop | Composed closed-receipt browser/parent evidence plus fixed-instant backend hours/closure calculations; no fixed-clock browser claim | pass | F.test_pause_and_closed_confirmation covers closed receipt with no scheduled reopening; V1 phone receipt displayed Tuesday Oct 20 next opening. H.test_hours_boundaries asserts exact November/March DST next openings; H.test_closure_union_newest_and_midday_reopen covers notice-adjusted reopening. |
| pre | repair-request | Intake paused: form replaced by both locations' call/text actions | 375 | 375px paused-card browser assertions | pass | R6 test_flows.py::test_pause_and_closed_confirmation[phone]: form absent; paused card visibly contains Bel Air tel:+14108368316 and Dundalk tel:+14433863800 plus sms:+14433863800. No call/text sent. |
| pre | repair-request | Email sender down: request saved, customer sees success, outbox shows failed, retry sends | desktop | Browser seeds a failed delivery after real intake to check failure/receipt UI; separate process-local mail tests exercise actual failure, synthetic reconnect and retry-to-sent | pass | F.test_failed_delivery_fixture_keeps_request_and_explains_disconnected_sender; L.test_disconnected_sender_does_not_lose_intake; L.test_delivery_outcomes; L.test_safe_retry_refresh_reauth_expired_lease_and_disconnect. Retry uses the real API/worker with a stubbed provider response; no real Gmail delivery or browser reconnect/retry click claimed. |
| pre | repair-request | Server error or offline: message, input and photos kept, retry works, call/text fallback shown | 375 | Real SQLite contention returns intake 503, plus actual browser offline recovery | pass | R6 test_acceptance_r6.py::test_real_intake_503_retains_photo_fields_fallback_and_retry[phone]: competing SQLite write lock causes actual 503/DATABASE_BUSY; fields/photo and both phone fallbacks retained; Try again after unlock produces one 201 with same idempotency key, one request/event and original photo. Offline test also verifies both telephone fallbacks and retained photo before recovery. |
| pre | repair-request | Refresh and back button mid-form keep draft; deep link to form works | 375 | Real browser navigation/reload/back with attached photo; expiry regressions | pass | F.test_offline_failure_refresh_deep_link_and_back_keep_draft; R.test_valid_last_seconds_photo_draft_keeps_attachment; R.test_expired_photo_draft_requires_reattachment; R.test_clear_during_processing_cancels_submit_and_new_form_works. |
| pre | repair-request | Demo mode: email to non-allowlisted address is preview-only, not sent | desktop | API worker test fails on any attempted provider call; browser confirms preview-only request mail | pass | L.test_demo_allowlist_encrypted_preview_and_no_send; F.test_bel_air_three_photos_receipt_emails_refresh_back; S.test_demo_customer_links_suppressed_and_exact_allowlist. |
| pre | repair-request | Form controls fit their cards at 375 px, with 200% text and visible focus | 375 | Committed-candidate parent inspection at doubled text and card-level bounds | pass | R5 visual-r5.md: final 375px header wraps cleanly, six controls contained by form card, visible solid focus outline. R.test_double_text_header_and_card_controls passed. |
| pre | repair-status | Staff sends estimate; customer email rendered with amount, estimate wording and link; status page shows it | desktop | Browser estimate confirmation/customer status plus authenticated rendered-mail reads; no sends | pass | F.test_staff_estimate_customer_response_ready_and_privacy checks $12.34 and final-price disclaimer in mail and the estimate page; V1 completed estimate-to-status with preview-only outbox. |
| pre | repair-status | Customer accepts estimate: status becomes waiting for drop-off with correct location route | 375 | Browser accept flow plus API state assertion and parent customer walkthrough | pass | F.test_staff_estimate_customer_response_ready_and_privacy[accept]; A.test_offers_responses_conflicts_and_no_private_note asserts awaiting_dropoff; V1 confirmed awaiting-dropoff after customer acceptance. |
| pre | repair-status | Customer declines and asks for a call: recorded once, second response blocked, staff sees it | 375 | Separate decline/callback browser variants plus API replay/concurrency guards | pass | F.test_staff_estimate_customer_response_ready_and_privacy[decline/request_call] reads staff response and verifies response controls removed after reload; A.test_visit_response_and_supersession; A.test_offers_responses_conflicts_and_no_private_note; E.test_two_responses_and_two_offers_cannot_overwrite. |
| pre | repair-status | Needs visit and not repairable statuses show correct copy and actions | 375 | Browser visit offer then not-repairable transition, plus backend branch rules | pass | F.test_needs_visit_and_not_repairable checks both customer headings and removes callback response after not-repairable; E.test_not_repairable_is_a_branch_and_leaving_it_requires_reason. |
| pre | repair-status | Staff marks ready with pickup location: customer page and email update, closure notice shown if active | 375 | Browser ready/active Dundalk notice plus both-location API wording regressions | pass | F.test_staff_estimate_customer_response_ready_and_privacy[accept] checks customer ready, Dundalk SMS and closure in page/mail; N.test_ready_status_and_mail_use_pickup_route checks Bel Air collection wording and Dundalk route in status/plain/HTML mail. V1 phone-counter ready confirmed after recording. |
| pre | repair-status | Lookup by reference plus email or phone last four; mismatches give identical generic error; rate-limited | desktop | Browser successful/mismatched lookups plus API uniform-error and throttling checks | pass | F.test_lookup_mismatch_phone_last4_expired_and_invalid_link; A.test_lookup_uniform_and_expiry_reopen; A.test_rate_limits_and_database_lock; S.test_forwarding_headers_cannot_bypass_lookup_limit. V1 also completed reference/last-four lookup. |
| pre | repair-status | Invalid token and closed-request expiry show generic page with lookup and call links | 375 | Browser invalid/expired capability recovery plus API expiry/token-rotation and parent lookup-page inspection | pass | F.test_lookup_mismatch_phone_last4_expired_and_invalid_link; A.test_lookup_uniform_and_expiry_reopen; V1 inspected public status/lookup at all three sizes. R.test_forget_clears_history_and_discards_old_events prevents old repair history leaking into another lookup. |
| pre | repair-status | Walk-in ticket without email or photos creates reference; "Text status link" opens prefilled sms link | 375 | Browser ticket creation and inspection of generated sms destination/body; no external messaging app or send | pass | F.test_walkin_phone_only_text_link_and_inbox_filters checks no email/photos and sms:+12025550123 with body; A.test_walkin_contact_actions_ready_and_search. V1 phone walk-in/ready completed; its non-allowlisted manual SMS was correctly blocked. |
| pre | repair-status | Status tracker uses words, no step numbers; internal notes never shown to customer | desktop | Parent final ready tracker and internal-note privacy walkthrough | pass | R5 visual-r5.md: word-only tracker and Collect your item copy inspected at 375px. Unique note added through staff UI; subsequent customer lookup/render contains no note. Existing API/browser privacy checks also pass. |
| pre | staff-admin | Every admin route rejects requests without a real Google session; no bypass in deployed image | desktop | Enumerate invalid sessions on every API method/collection and guarded HTML; ordinary signed synthetic Google-bound sessions, real HTTP and runtime fixture exclusion | pass | S.test_every_admin_api_requires_current_google_session[anonymous/expired/revoked/inactive/wrong_version/unbound]; S.test_privileged_html_paths_are_guarded; F.test_uninvited_and_expired_google_sessions_rejected_in_real_http; R4 launcher runtime exclusion and R1 check_backend.py scan. Tests establish enforcement/image contents, not live Google sign-in. |
| pre | staff-admin | Synthetic initial-admin sign-in and Viewer invite: email binding, expiry and wrong-account refusal; actual Google acceptance remains live | desktop | Normal signed-session browser fixtures plus process-local OAuth protocol/initial-admin/invite tests; manual Google removed from this phase only | pass | S.test_google_state_binding_once_and_initial_account; S.test_invite_bound_wrong_used_expired_and_sub_mismatch; S.test_oauth_verifier_nonce_and_provider_failure; F.test_viewer_inbox_filters_estimates_management_denied. Real account sign-in/invitation remains mandatory under each live staff-auth row as explained above. |
| pre | staff-admin | Viewer can update requests and estimates but not settings, hours, notices or team | desktop | Viewer browser access/denial plus actual Viewer API writes and exhaustive management-route denial | pass | F.test_viewer_inbox_filters_estimates_management_denied; A.test_offers_responses_conflicts_and_no_private_note creates estimate as Viewer; A.test_walkin_contact_actions_ready_and_search updates ready as Viewer; S.test_viewer_denied_all_management_routes. |
| pre | staff-admin | Last admin cannot be removed | desktop | Concurrent authenticated member removals against real database transaction guard | pass | S.test_last_admin_atomic_race: one 204, one 409 LAST_ADMIN, exactly one active Google-bound Admin survives. |
| pre | staff-admin | Inbox filters, search and empty states; new requests first | 375 | Browser filter/search/empty-state flows plus API sort/keyset checks | pass | F.test_walkin_phone_only_text_link_and_inbox_filters; F.test_viewer_inbox_filters_estimates_management_denied; R.test_waiting_badge_matches_unanswered_offer; P.test_inbox_priority_and_status_exit_with_normalized_query; P.test_all_lists_keysets_survive_insert_and_boundary_removal[inbox]. V1 searched exact and absent references. |
| pre | staff-admin | Two staff edit one request: second save gets conflict message and keeps typed text | desktop | Separate signed-session writers, visible conflict/reload preservation, deliberate stale-draft reapply regressions | pass | F.test_conflict_and_expired_session_preserve_staff_draft; R.test_request_restored_draft_keeps_version_until_reapply; R.test_hours_stale_draft_comparison_then_deliberate_reapply; R.test_settings_load_latest_and_reload_keep_old_base. V1 conflict/load-latest/resave preserved note text. |
| pre | staff-admin | Session expires mid-estimate: same-member local re-entry keeps draft; actual Google re-sign-in remains live | desktop | Same-member signed synthetic session restoration through normal login return route | pass | R6 test_acceptance_r6.py::test_same_member_session_return_retains_estimate_and_stale_guard[desktop]: expired estimate returns 401; original returnTo and draft retained; normal login validates restored same-member session; concurrent version change blocks stale send until explicit Reapply; one confirmed send creates one offer/event. Provider-disabled start returns503; actual Google remains live. |
| pre | staff-admin | Photos only reachable with staff session | desktop | Actual sanitized-photo fetch with anonymous, Viewer, wrong-request and public-bearer authorization checks | pass | U.test_conversion_metadata_sandbox_and_private_access[JPEG/PNG/WEBP]; S.test_public_bearer_does_not_authorize_photos; R1 real HTTP private-photo probe. |
| pre | staff-admin | Admin usable one-handed on phone: open request, zoom photo, send estimate, mark ready | 375 | Recorded committed-candidate phone photo/estimate/ready and full tablet detail inspection | pass | R5 visual-r5.md: 500x1291 portrait fits 349x697 frame; actual-size scrolls and Escape restores focus. Confirmed $45 estimate and ready state. Tablet detail inspected top-bottom; final recording 330c99a8-36da-4ee4-b022-090be15767dd retained privately. |
| pre | location-notices | Bel Air open, closing soon, closed with next opening across Tue–Sat hours and DST change | desktop | Fixed-instant backend boundary/DST/notice tests composed with real browser hours editor/public rendering; no browser clock replacement | pass | H.test_hours_boundaries; H.test_offset_fold_gap_and_unknown_regular_hours; H.test_closure_union_newest_and_midday_reopen; F.test_hours_editor_validation_and_saved_state; F.test_pause_and_closed_confirmation; V1 current hours/cards/receipt inspected. |
| pre | location-notices | Dundalk never shows open; always appointment with call and text 443-386-3800; legacy number absent site-wide | 375 | Backend boundary invariants, browser contact links and completed source/page scan | pass | H.test_hours_boundaries asserts appointment_only/no weeklyHours for every instant; F.test_locations_notice_every_surface_fallback_links_and_containment checks current links/no legacy number; Review R2 scanned all frontend source; V1 home/form/status inspected. |
| pre | location-notices | Admin posts closure notice for Bel Air: shows on home, card, form and ready status; expires on its own | desktop | Composed browser notice creation, both-location public surfaces, ready-notice flow and real-time expiry; parent editor walkthrough | pass | M.test_notice_editor_invalid_time_and_saved_public_banner (Bel Air); F.test_locations_notice_every_surface_fallback_links_and_containment (both locations, home and form); F.test_staff_estimate_customer_response_ready_and_privacy[accept] (Dundalk ready page/mail); N.test_ready_status_and_mail_use_pickup_route (both pickup routes); M.test_public_notice_expires_without_refresh (Bel Air). V1 notice preview/create/delete and location cards inspected. |
| pre | location-notices | Hours data failure falls back to "call before visiting", never a wrong state | 375 | Abort real browser locations request and inspect fallback; parent current/fallback source review | pass | F.test_locations_notice_every_surface_fallback_links_and_containment aborts /api/v1/locations and checks Call before visiting; reviewed fallback sets Bel Air unknown and preserves Dundalk appointment_only. |
| pre | location-notices | Hours editor and notice editor validation | desktop | Actual browser invalid input, focus, corrected save and public notice readback; backend validation | pass | F.test_hours_editor_validation_and_saved_state; M.test_notice_editor_invalid_time_and_saved_public_banner; A.test_settings_retention_notices_and_validation; V1 notice empty validation/preview/create/delete. Final hands-on hours-bottom inspection remains under pre 45. |
| pre | call-text, maps-directions, social-links | tel, sms, Maps and social links open the right destinations; no placeholder prices anywhere | 375 | Built required-link/claim scan, browser href inspection and previously opened exact source destinations; no calls/texts sent | pass | R4 app/scripts/check.mjs with app/xs-check.json checks exact tel/sms/Maps/social URLs and public placeholder-price patterns; F.test_locations_notice_every_surface_fallback_links_and_containment; sources S14–S17 record actual Maps/profile visits. Review R2 found no public price list. Native dialer/SMS dispatch is not claimed. |
| pre | all | Records and photos survive container replacement; backup restore including uploads tested once | n/a | Completed isolated real Docker replacement/full-volume restore plus environment-bound backup harness; no host restore claim | pass | Backend R1 scripts/check_backend.py and tests/e2e/api_probe.py passed twice: HTTP record/photo, SQLite integrity and matching upload/key hashes after replacement/restore. A.test_replacement_and_complete_data_restore; backend R2 scripts/test_backup.py 61 passed and updater 54 passed. Host Docker/HTTPS calls were mocked in R2; updated host scripts still need installation/live verification. |
| pre | all | No console errors or failed requests; main pages fast on mid-range phone | 375 | Eleven real candidate routes; 4x CPU, 40 ms latency and 1.5 Mbps download phone emulation; not a physical handset or Oracle latency benchmark | pass | M.test_main_routes_no_browser_errors_or_missing_resources asserts HTTP200, visible H1, DOMContentLoaded under 10 s and no console/response/network errors on each route; shared page fixture rejects page errors. V1 interactive phone flow recordings supplement this bounded performance evidence. |
| pre | all | Hands-on customer and staff walkthrough with screen recording of each main flow | desktop and 375 | Completed parent main-flow recordings and affected-screen visual acceptance | pass | R1 customer, home, desktop staff and phone counter recordings plus R5 final phone photo/estimate/ready recording. R5 accepts affected 1440/820/375 layouts, 200% text, stale draft comparison/reapply, retention preview, hours bottom, word-only ready tracker, note privacy, outbox/inbox pagination and representative keyboard/hover controls. R4 motion/print-media/PDF checks pass; no physical-print claim. Details in private visual-r1.md and visual-r5.md. |
| live | repair-request | derek-dev: synthetic request with photo; Derek's test inbox receives customer and staff email | 375 | Real Chrome at 375px, protected metadata and actual Gmail Inbox | pass | R9: photo ready 0.919s (plus genuine 12MP HEIC 2.807s in R7); normal UI request saved; customer receipt and staff alert both visibly received in the allowlisted Inbox. All five workflow messages per environment received. Raw photo removed; exact synthetic request/photo purged after backup. |
| live | repair-status | derek-dev: estimate sent, accepted, marked ready; customer page updates; test records removed | 375 | Real Chrome customer/staff flow and exact-ID cleanup | pass | R9: $12.34 estimate sent, accepted, waiting-for-drop-off then ready at Bel Air; 375px customer page updated. No contact details, photos or internal note exposed. Estimate/response/ready messages observed in actual Inbox. Exact synthetic requests/photos removed; audit and backups preserved; zero requests remain. |
| live | staff-admin | derek-dev: Derek signs in with Google; unauthenticated admin request rejected | desktop | Authentic Chrome Google login and same-member return; unauthenticated HTTPS | pass | R9: real Admin Google login; second-tab sign-out revokes session, failed send retains draft, normal Google re-entry restores amount/text and allows confirmed send. Nine admin collections reject anonymous access with401. Separate-account live Viewer acceptance excluded by user; local coverage only. Temporary invitation withdrawn, no mail sent, sole Admin preserved. |
| live | location-notices | derek-dev: notice posted and expired; open state correct for current time | desktop | Real Admin notice creation and observed automatic expiry | pass | R9: temporary Bel Air notice created, visible on customer status banner/card, then automatically disappeared without refresh at its end. Current Saturday closed/next Tuesday9am restored; Dundalk appointment-only4433863800. No active test notice remains. |
| live | repair-request | abdul-dev: synthetic request with photo; test inbox receives emails | 375 | Real Chrome at 375px, protected metadata and actual Gmail Inbox | pass | R9: photo ready 1.244s; normal UI request saved; customer receipt and staff alert both visibly received in the allowlisted Inbox. All five workflow messages per environment received. Raw photo removed; exact synthetic request/photo purged after backup. |
| live | repair-status | abdul-dev: estimate to ready flow; test records removed | 375 | Real Chrome customer/staff flow and exact-ID cleanup | pass | R9: $12.34 estimate sent, accepted, waiting-for-drop-off then ready at Bel Air; 375px customer page updated. No contact details, photos or internal note exposed. Estimate/response/ready messages observed in actual Inbox. Exact synthetic requests/photos removed; audit and backups preserved; zero requests remain. |
| live | staff-admin | abdul-dev: Google sign-in works; unauthenticated admin request rejected | desktop | Authentic Chrome Google login and same-member return; unauthenticated HTTPS | pass | R9: real Admin Google login; second-tab sign-out revokes session, failed send retains draft, normal Google re-entry restores amount/text and allows confirmed send. Nine admin collections reject anonymous access with401. Separate-account live Viewer acceptance excluded by user; local coverage only. Temporary invitation withdrawn, no mail sent, sole Admin preserved. |
| live | location-notices | abdul-dev: notice and open state correct | desktop | Real Admin notice creation and observed automatic expiry | pass | R9: temporary Bel Air notice created, visible on customer status banner/card, then automatically disappeared without refresh at its end. Current Saturday closed/next Tuesday9am restored; Dundalk appointment-only4433863800. No active test notice remains. |
| live | repair-request | production: synthetic request with photo; test inbox receives emails; record deleted after | 375 | Real Chrome at 375px, protected metadata and actual Gmail Inbox | pass | R9: photo ready 1.759s; normal UI request saved; customer receipt and staff alert both visibly received in the allowlisted Inbox. All five workflow messages per environment received. Raw photo removed; exact synthetic request/photo purged after backup. |
| live | repair-status | production: estimate to ready flow; test records deleted, production data clean | 375 | Real Chrome customer/staff flow and exact-ID cleanup | pass | R9: $12.34 estimate sent, accepted, waiting-for-drop-off then ready at Bel Air; 375px customer page updated. No contact details, photos or internal note exposed. Estimate/response/ready messages observed in actual Inbox. Exact synthetic requests/photos removed; audit and backups preserved; zero requests remain. |
| live | staff-admin | production: Derek signs in with Google; unauthenticated admin request rejected | desktop | Authentic Chrome Google login and same-member return; unauthenticated HTTPS | pass | R9: real Admin Google login; second-tab sign-out revokes session, failed send retains draft, normal Google re-entry restores amount/text and allows confirmed send. Nine admin collections reject anonymous access with401. Separate-account live Viewer acceptance excluded by user; local coverage only. Temporary invitation withdrawn, no mail sent, sole Admin preserved. |
| live | location-notices | production: open state correct; no notice left active | desktop | Real Admin notice creation and observed automatic expiry | pass | R9: temporary Bel Air notice created, visible on customer status banner/card, then automatically disappeared without refresh at its end. Current Saturday closed/next Tuesday9am restored; Dundalk appointment-only4433863800. No active test notice remains. |
| live | all | Each environment: backup timer active; DEMO_MODE=true; previews noindex | n/a | SSH host state, branch isolation and independent HTTPS | pass | R9: all3 backup/update timers enabled/active, DEMO_MODE=true, noindex, root-only runtime, original exact allowlists and independent data/keys/OAuth clients. Only Derek changed for the KB-only isolation commit; production/Abdul and 12 siblings, nine HTTPS revisions and gateway unchanged. Final heads verified in private receipts. |
