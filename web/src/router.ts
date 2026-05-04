import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

import Home from "@/pages/Home.vue";
import Vaults from "@/pages/Vaults.vue";
import VaultNew from "@/pages/VaultNew.vue";
import VaultDetail from "@/pages/VaultDetail.vue";

import { useAuthStore } from "@/store/auth";

const routes: RouteRecordRaw[] = [
  { path: "/", name: "home", component: Home },
  { path: "/vaults", name: "vaults", component: Vaults, meta: { requiresAuth: true } },
  {
    path: "/vaults/new",
    name: "vault-new",
    component: VaultNew,
    meta: { requiresAuth: true },
  },
  {
    path: "/vaults/:id",
    name: "vault-detail",
    component: VaultDetail,
    meta: { requiresAuth: true },
  },
  { path: "/:pathMatch(.*)*", redirect: { name: "home" } },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const auth = useAuthStore();
    if (!auth.isAuthenticated) {
      return { name: "home", query: { next: to.fullPath } };
    }
  }
});
