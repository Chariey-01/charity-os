// Worker entry point. Only the default export may live here: workerd treats
// every named export of the main module as an entry point. See src/edge.js
// and src/scheduler.js.
import { handleRequest } from "./edge.js";
import { forgetNextDue, invalidates, runScheduled } from "./scheduler.js";

export default {
  async fetch(request, env, ctx) {
    const response = await handleRequest(request, env);
    if (response.ok && invalidates(request)) ctx?.waitUntil?.(forgetNextDue(env));
    return response;
  },
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(runScheduled(env, controller.scheduledTime ?? Date.now()));
  },
};
