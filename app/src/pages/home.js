import '../styles/tokens.css';
import '../styles/base.css';
import '../styles/forms.css';
import '../styles/home.css';
import { initChrome } from '../lib/chrome.js';
import { initMotion } from '../lib/motion.js';
import { initLookup } from '../lib/lookup.js';

initChrome();
initMotion();
initLookup(document.querySelector('[data-lookup]'));
