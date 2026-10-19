import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import hooks from 'eslint-plugin-react-hooks';
export default tseslint.config({ignores:['dist','node_modules']},js.configs.recommended,...tseslint.configs.recommended,{files:['src/**/*.{ts,tsx}'],plugins:{'react-hooks':hooks},rules:{...hooks.configs.recommended.rules,'@typescript-eslint/no-explicit-any':'error'}});
