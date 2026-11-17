// The viewer's light/dark choice, kept in <html data-theme> and localStorage.
export const THEME_KEY = "eval-theme";

/** Runs in <head> before paint, so a stored light theme never flashes dark. Dark unless the
 *  viewer chose light; the system setting is ignored on purpose. */
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}")}catch(e){}document.documentElement.dataset.theme=t==="light"?"light":"dark"`;
