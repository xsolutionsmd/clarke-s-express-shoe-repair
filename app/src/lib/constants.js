// Compile-time enums and customer wording shared by the public site and the admin.
// Values mirror docs/API.md "Shared values"; labels are words, never numbered steps.

export const ITEM_TYPES = [
  ['shoes', 'Shoes'],
  ['boots', 'Boots'],
  ['handbag_purse', 'Handbag or purse'],
  ['belt_strap', 'Belt or strap'],
  ['leather_garment', 'Leather jacket or garment'],
  ['luggage', 'Luggage'],
  ['baseball_glove', 'Baseball glove'],
  ['other_leather', 'Other leather item'],
  ['keys', 'Keys (ask us)'],
];

export const WORK_TYPES = [
  ['soles_heels', 'Soles or heels'],
  ['heel_tips', 'Heel tips'],
  ['stretch_fit', 'Stretching or fit'],
  ['orthopedic_modification', 'Lift or orthopedic modification'],
  ['stitching', 'Stitching'],
  ['zipper', 'Zipper'],
  ['dye_color', 'Dye or colour'],
  ['clean_condition', 'Clean and condition'],
  ['straps_hardware', 'Straps or hardware'],
  ['not_sure', 'Not sure'],
];

export const LOCATIONS = {
  bel_air: { name: 'Bel Air', long: 'Bel Air (main repair shop)', phone: '410-836-8316', tel: 'tel:+14108368316', sms: null },
  dundalk: { name: 'Dundalk', long: 'Dundalk (by appointment)', phone: '443-386-3800', tel: 'tel:+14433863800', sms: 'sms:+14433863800' },
};

export const STATUS = {
  new: 'Received',
  reviewing: 'Being reviewed',
  estimate_sent: 'Estimate ready',
  needs_visit: 'Please bring it in',
  not_repairable: 'We can’t repair this',
  awaiting_dropoff: 'Waiting for drop-off',
  in_shop: 'In the shop',
  in_progress: 'Being repaired',
  ready: 'Ready for pickup',
  picked_up: 'Picked up',
  cancelled: 'Closed',
};

// Forward order for the customer progress line and staff "moving back" hints.
export const STATUS_ORDER = ['new', 'reviewing', 'estimate_sent', 'needs_visit', 'awaiting_dropoff', 'in_shop', 'in_progress', 'ready', 'picked_up'];
export const CLOSED = new Set(['picked_up', 'cancelled']);

export const RESPONSE_LABELS = {
  accept: 'I’ll bring it in',
  decline: 'No thanks',
  request_call: 'Please call me',
};

export const label = (pairs, value) => (pairs.find(([v]) => v === value) || [null, value])[1];
export const itemLabel = value => label(ITEM_TYPES, value);
export const workLabel = value => label(WORK_TYPES, value);
export const locationName = id => LOCATIONS[id]?.name || id || '';
export const statusLabel = status => STATUS[status] || status;
