/* ES-module wrapper that exports the shared decision-explorer UI renderer.
   The renderer itself is byte-identical to the static frontend's
   assets/js/decisions-ui.js (DOM-based, framework-agnostic). */
export { renderDecisions } from "./decisions-ui-shared.js";
