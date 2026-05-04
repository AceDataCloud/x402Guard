import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import tsParser from "@typescript-eslint/parser";
import vueParser from "vue-eslint-parser";

export default [
  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.ts", "**/*.vue"],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 2022,
        sourceType: "module",
      },
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        TextEncoder: "readonly",
        atob: "readonly",
        btoa: "readonly",
        setTimeout: "readonly",
        Uint8Array: "readonly",
        process: "readonly",
        console: "readonly",
      },
    },
    rules: {
      "vue/multi-word-component-names": "off",
      "no-unused-vars": "off",
      "no-undef": "off",
    },
  },
  { ignores: ["dist", "node_modules", "tests-e2e/playwright-report"] },
];
