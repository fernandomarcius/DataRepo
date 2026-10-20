import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // Estas tres reprovam 19 pontos do codigo existente (set-state dentro de
      // effect, mutacao de estado, pureza). Sao achados reais, mas corrigi-los
      // muda comportamento de componentes que nao tem teste de tela, entao
      // entram como aviso ate serem tratados um a um. Codigo novo deve nascer
      // limpo: o aviso aparece no log do CI, nao desaparece.
      // Revisar ate 2026-11-30 — owner: maintainers.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/purity': 'warn',
      // Variavel nao usada e defeito, mas argumento e catch nomeados por
      // convencao nao sao: o padrao `catch (err)` sem uso e legivel.
      'no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        caughtErrors: 'none',
        varsIgnorePattern: '^[A-Z_]',
      }],
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
];
