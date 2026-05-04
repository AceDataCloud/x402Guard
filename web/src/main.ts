// Buffer polyfill — MUST be the first import so it lands in the module
// graph before @solana/web3.js (transitively imported via store + wallet).
import "./polyfills";

import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import { router } from "./router";

import "./styles/global.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
