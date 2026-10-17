// Lint configuration (kept under src/ with the rest of the frontend-owned sources).
import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    files: ['**/*.js', '**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: { ...globals.browser },
    },
    rules: {
      'no-unused-vars': ['error', { args: 'none', caughtErrors: 'none' }],
      'no-restricted-properties': ['error',
        { property: 'innerHTML', message: 'Build DOM with h() so user text is never parsed as HTML.' },
        { property: 'outerHTML', message: 'Build DOM with h().' }],
      'no-restricted-syntax': ['error',
        { selector: "CallExpression[callee.property.name='insertAdjacentHTML']", message: 'Build DOM with h().' }],
      eqeqeq: ['error', 'smart'],
      'prefer-const': 'error',
    },
  },
  {
    files: ['vite.config.mjs', 'eslint.config.mjs'],
    languageOptions: { globals: { ...globals.node } },
  },
];
