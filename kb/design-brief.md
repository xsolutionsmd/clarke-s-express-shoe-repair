# Design brief

Research brief, observed 2026-10-17. Visitor needs below are **inferred from public evidence**. They do not establish owner-approved features, integrations or a selected visual template.

## Visitor job and primary action

Find out whether a valued shoe, boot, bag or leather item can be repaired, then reach the right shop with enough information to arrange assessment. The business advertises detailed estimates and several repairs whose feasibility depends on the item. [S2][S3][S5]

**Inferred primary action:** contact Bel Air about a repair at 410-836-8316. For the Dundalk location, make the separate call/text appointment route to 443-386-3800 clear. The existing inquiry form is an alternative contact route, not a confirmed reservation or quote engine. [S1][S4][S14][S15]

## Content plan

| Visitor question | Evidence-based content |
|---|---|
| Can you help with my item? | Organize documented services around footwear, bags/leather, zippers and fit modifications. Explain assessment is item-specific. [S2][S3][S5] |
| Why trust you with it? | Family business founded in 1991, owner/craftsman story, attributable review excerpts and actual prior work. Avoid an unverified award badge. [S1][S6][S7][S14][S16][S20] |
| What will it cost and when can I collect it? | Describe the published estimate approach; exact prices, accepted rush jobs and current lead times are unknown. Never copy the placeholder pricing table. [S2][S3][S5][S11] |
| Where should I go? | Distinct location information: Bel Air rear entrance/Burns Alley and regular hours; Dundalk appointment notice and call/text number. [S1][S4][S14][S15] |
| How do I get help? | Correct contact destinations, useful inquiry context, and a clear distinction between a request and confirmed arrangements. Backend workflow/owner response times need confirmation. [S1][S4] |
| Are there exceptions? | An owner-maintainable source of holiday/weather closure information would answer a demonstrated need; this is an inference for later feature evaluation. Do not carry forward expired closure posts. [S16][S18] |

## Evidence for later functional choices

**Observed:** two simple inquiry forms; direct phone/text appointment instructions; a Messenger link; no working public booking calendar, repair-status lookup, photo intake or ecommerce flow found in the inspected site. [S1][S4][S10][S11]

**Inferred needs to evaluate:** item/service context, damage description, preferred location/contact channel, estimated timing, and an understandable follow-up process. The owner letter emphasizes avoiding communication breakdowns. Any upload, scheduling, status or administration feature still needs selection and an operating workflow; this research does not adopt it. [S2][S4][S5][S6][S14][S15]

## Template site
Selected 2026-10-17 by the template stage (Claude Opus 5.5 high) after live desktop
(1440) and phone (375) inspection. Not a client approval.

**Template: The Restory, https://www.the-restory.com/us-en** (luxury leather-goods
restoration atelier), with its photo quote form at
https://go.the-restory.com/request-a-quote. It won on polish: quiet editorial serif
display, one black square CTA, wide margins, large tightly framed craft photography, a
keyboard-operable before/after slider, and a photo intake that is a single calm card
rather than a wizard. Its flow is the closest premium match to ours: describe the issue,
add photos, leave details, staff assess and reply with a quote, emails at each stage,
order history behind an account. It holds up at 375 px (no horizontal overflow; form
controls inset 15 px from a full-bleed card). Behavior evidence is in
[features.md](features.md#template-flow-notes).

**Runners-up**
- Rago Brothers, https://www.ragobrothers.com/ (family shop since 1911, the closest
  in scale): best flow coverage (guest mail-in form, optional photo assessment with
  guided slots, customer account, a retailer login on a repair-ticket platform), but a
  dated pastel template with a boxed hero and heavy banner. We adopt its guided photo
  wording, not its look.
- Leather Spa, https://leatherspa.com/: a repair wizard, estimates, status and
  payment, all behind a password account; a busy promo carousel with script type.
  Confirms "check the status of your repairs" as a category norm.
- SoleHeeled, https://soleheeled.com.au/: a price-first Typeform "instant quote" with
  Stripe and numbered how-it-works steps; it conflicts with our no-prices rule and looks
  mid-tier.

**Limits:** no inspected site exposes its staff admin publicly (Rago's retailer and
customer logins, Leather Spa and Restory accounts are all gated; no accounts were
created). The admin follows the Oasis pattern, dressed in this public visual language.
The Restory sells a priced package before photos; we keep its intake card and quote
reply, and drop pricing, cart and checkout entirely.

**Adopted traits (structure and quality only; no Restory text, photos, logo or code)**
- *Navigation:* slim white header, wordmark left, four text links centered
  (Repairs, Our work, Visit, Repair status), one black "Start a repair request"
  button right; phone: wordmark centered, menu left, call icon right. An active
  closure notice sits above the header as a single quiet band.
- *Home section order:* split hero (full-height photo on one side, serif headline,
  one sentence, one black CTA "Send photos for an estimate", text link to call Bel
  Air) → a large serif statement in the shop's own voice → a work spread (before/after
  slider only with an aligned pair, see media below) beside a tall detail photo →
  service tiles (soles and heels; stretching and fit; bags and
  leather goods; dye, clean and condition), square photos with serif titles and an
  "Ask about this repair" link that preselects the form → how a request works, three
  word-titled columns with no numbers (Send photos, We reply with an estimate, Drop off
  and collect) → two location cards → status lookup band → craftsman story → compact
  footer.
- *Type scale:* high-contrast display serif, regular weight, tracking about 0.08em:
  hero 88/96 desktop, 44/52 phone; section titles 48/58 desktop, 32/40 phone; card
  titles 24/29. Body: humanist sans 16/24 with slight positive tracking (about
  0.02em); labels and buttons in uppercase sans 13-14 px, tracking 0.08em.
- *Spacing rhythm:* 8 px base; 40 px page gutters at 1440 (content up to 1360),
  20 px on phones; section spacing 128 px desktop, 72 px phone; form card 640 px wide
  on a tinted page with 48 px inner padding (24 px on phones, never full-bleed controls
  touching the card edge).
- *Controls:* square black primary buttons (2 px radius), quiet text-link secondaries,
  1 px input borders dark enough for 3:1 non-text contrast (the template's pale
  hairlines are not copied), 48 px control height, dashed dropzone.
- *Motion character:* restrained. 150 ms colour/border transitions; images fade and
  rise 8 px over 600 ms on entering view and replay on re-entry; slow 1.03 image scale
  on tile hover; before/after handle follows pointer, arrow keys and Home/End. All off
  under reduced motion. No carousels or moving ribbons.

**Client-media mapping** (sha prefixes in [media.md](media.md); originals stay private)
- Hero: `d600e63f8c01` (tan monk straps and sole, 2048 px), cropped to shoe and sole,
  losing the busy pegboard. Phone hero: `6715d5e4ef37` (black cap-toe, red sole) as a
  vertical crop.
- Statement and detail: `30ab62c60233`, `1a4378dac4c8`.
- Before/after: the slider needs a genuinely aligned before and after shot of one item.
  `96bcc461523e` is two shoes side by side with no stated direction, so it is shown as a
  static pair captioned only by what is visible. The build round may look for an aligned
  pair among the Instagram carousel slides in the private library; if none exists, that
  block becomes a two-photo detail spread, never a fake slider.
- Service tiles: soles `5748995db348` / `c1552b8d1158`; fit `d331be06df16`
  (third-party provenance noted); leather `46257a13947a` / `f4985fc6d5b6`; dye
  `96bcc461523e`.
- Visit cards: Bel Air `27e3eddd0df8` (rear shop, pharmacy landmark visible), Dundalk
  `dc2c45602e65`.
- Craftsman: `a5a7d729cc9f`, cropped around face and machine; `48128ddc0e6e`
  secondary. Logo: `4899edee3a67` (black mark) on light grounds.
- Shop photos have busy retail backgrounds. Crop tight to leather and use a warm paper
  ground so the photos read as one set; never generated or competitor imagery.

## Visual direction

Existing source cues: yellow brand/avatar treatment, a personal cobbler voice and detailed examples of repaired footwear/leather. [S1][S7][S17]

**Chosen direction (2026-10-17, template stage):** a quiet workshop atelier. A warm
paper ground (`#F5F1EA`), deep ink text (`#1B1A17`), oxblood accent (`#6B1E1A`, from
the red wordmark and resoled heels) used for links, focus and status emphasis only, and
warm grey hairlines (`#D9D2C5`). The brand yellow appears once, small, as the open-now
pill (`#EBD46A` on ink text), not as a header colour. Free self-hosted fonts (no
external runtime font requests): Libre Caslon Display for headings, Hanken Grotesk for
body, labels and controls. Tokens and component rules live in
[DESIGN.md](../DESIGN.md). Stitch outcome: one bounded attempt timed out with no screen
(recorded in the private run note); implementation proceeds from these references.

## Accepted decisions and corrections

No new client-specific design approval was obtained in this research. Preserve the standing rules below. The factual content hierarchy should favor the live appointment notice and corroborated Maps details over stale buttons, directories and indexed copies. Conflicts and limits are recorded in [open-questions.md](open-questions.md). [S1][S4][S12][S13][S14][S15]

## X Solutions standing design rules

- Thoughtful, distinctive, professional and clean: strong typography, authentic
  photography, smooth restrained motion, enjoyable interaction; necessary copy only.
- No decorative numbering: no section ordinals, numbered badges, photo prefixes or
  counters such as 01 / 02. Factual numbers (prices, phone, dates) are fine.
- Choose photos for composition, quality, real work shown, variety and recency across
  the whole history, not just the newest posts. Never present generated or competitor
  work as the client's.
- Check every form control against its containing card (including padding) on narrow
  phones, with enlarged text and focus states; page-level overflow checks are not enough.
- Native inputs, keyboard access, visible focus, reduced-motion support and a pause
  control for ongoing decorative movement.
- Consistent SVG arrows/icons (no text glyphs or emoji arrows). No visitor-facing demo,
  preview or "functionality" banners and no repeated disclaimers.
- Optimise without degrading the experience: right-sized media, lazy loading, no
  needless browser work.
