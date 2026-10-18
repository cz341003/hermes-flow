/* Minimal jsx-runtime backed by the host React instance. */
const R = window.__HERMES_PLUGIN_SDK__.React;

function make(type, props, key) {
  if (key !== undefined) {
    props = Object.assign({}, props);
    props.key = key;
  }
  return R.createElement(type, props);
}

export const Fragment = R.Fragment;
export const jsx = make;
export const jsxs = make;
export const jsxDEV = make;
export default { Fragment: R.Fragment, jsx: make, jsxs: make, jsxDEV: make };
