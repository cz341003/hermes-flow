/* Host SDK does not expose ReactDOM. React Flow only calls createPortal for
 * EdgeLabelRenderer / NodeToolbar / ViewportPortal, which this editor does not use.
 * Return children inline as a safe fallback. */
export const createPortal = function (children) { return children; };
export const flushSync = function (fn) { return fn(); };
export const unstable_batchedUpdates = function (fn) { return fn(); };
export const findDOMNode = function () { return null; };
export default { createPortal, flushSync, unstable_batchedUpdates, findDOMNode };
