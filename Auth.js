/**
 * Diagnos — shared auth state
 *
 * Stores the real session token (JWT) and user info returned by the backend
 * after /auth/signup, /auth/signin, or /auth/google. localStorage is the
 * simplest place to keep this for a frontend-only app with no server-rendered
 * pages — every page on this origin can read it.
 *
 * isSignedIn() only checks "is there a token stored", not "is it still
 * valid" — an expired token will be rejected by the backend on the next
 * API call, at which point callers should treat a 401 as signed-out and
 * call DiagnosAuth.signOut().
 */
(function (window) {
  'use strict';

  const TOKEN_KEY = 'diagnos_token';
  const USER_KEY = 'diagnos_user';

  function isSignedIn() {
    try {
      return !!localStorage.getItem(TOKEN_KEY);
    } catch (e) {
      // localStorage unavailable (e.g. privacy mode) — fail closed, treat as signed out
      return false;
    }
  }

  function getToken() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch (e) {
      return null;
    }
  }

  function getUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  /**
   * Call after a successful signup/signin/google response.
   * @param {string} token - JWT returned by the backend
   * @param {{id: string, name: string, email: string}} user
   */
  function signIn(token, user) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
    } catch (e) {}
  }

  function signOut() {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch (e) {}
  }

  /**
   * Guards a page that requires sign-in. Call at the top of any protected page.
   * If not signed in, redirects to signin.html and remembers where to return to.
   */
  function requireSignIn(returnTo) {
    if (!isSignedIn()) {
      const dest = returnTo || (window.location.pathname.split('/').pop() || 'index.html');
      window.location.href = 'signin.html?redirect=' + encodeURIComponent(dest);
    }
  }

  /**
   * Wires up any element with class "js-run-diagnosis" so clicking it
   * goes to diagnosis.html if signed in, or signin.html (with a redirect back) if not.
   */
  function guardDiagnosisLinks() {
    document.querySelectorAll('.js-run-diagnosis').forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (!isSignedIn()) {
          e.preventDefault();
          window.location.href = 'signin.html?redirect=diagnosis.html';
        }
        // if signed in, let the normal href navigation to diagnosis.html proceed
      });
    });
  }

  /**
   * Shows/hides nav elements based on auth state.
   * Expects optional elements by id: navSignInBtn (hidden when signed in),
   * navUserMenu (shown when signed in).
   */
  function reflectNavState() {
    const signInBtn = document.getElementById('navSignInBtn');
    const userMenu = document.getElementById('navUserMenu');
    const signedIn = isSignedIn();

    if (signInBtn) signInBtn.style.display = signedIn ? 'none' : '';
    if (userMenu) userMenu.style.display = signedIn ? '' : 'none';
  }

  /**
   * Convenience wrapper for calling protected backend endpoints — attaches
   * the stored token automatically. Throws nothing special on 401; callers
   * should check response.status themselves and call signOut() if needed.
   */
  async function authFetch(url, options) {
    options = options || {};
    const headers = Object.assign({}, options.headers || {}, {
      Authorization: 'Bearer ' + (getToken() || ''),
    });
    return fetch(url, Object.assign({}, options, { headers }));
  }

  window.DiagnosAuth = {
    isSignedIn: isSignedIn,
    getToken: getToken,
    getUser: getUser,
    signIn: signIn,
    signOut: signOut,
    requireSignIn: requireSignIn,
    guardDiagnosisLinks: guardDiagnosisLinks,
    reflectNavState: reflectNavState,
    authFetch: authFetch,
  };
})(window);