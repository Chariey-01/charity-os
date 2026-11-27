// Worker entry point. Only the default export may live here: workerd treats
// every named export of the main module as an entry point. See src/edge.js.
import { handleRequest } from "./edge.js";

export default { fetch: handleRequest };
