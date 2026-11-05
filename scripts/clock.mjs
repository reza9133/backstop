// One clock for the live run. Real runs use the wall clock. The offline rehearsal sets TIME_SCALE (for example 60)
// so that minutes of waiting pass in seconds; the rehearsal backend reads the same clock.
const SCALE = Math.max(1, Number(process.env.TIME_SCALE) || 1);
const START = Date.now();
export const scale = SCALE;
export const nowSeconds = () => Math.floor((START + (Date.now() - START) * SCALE) / 1000);
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms / SCALE));
