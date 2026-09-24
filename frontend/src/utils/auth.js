// ─────────────────────────────────────────────────
// Local Storage Helpers
// ─────────────────────────────────────────────────
export const setToken = (token) => localStorage.setItem('token', token);
export const getToken = () => localStorage.getItem('token');
export const removeToken = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
};
export const isAuthenticated = () => !!getToken();

export const setUser = (user) => localStorage.setItem('user', JSON.stringify(user));
export const getUser = () => {
  const user = localStorage.getItem('user');
  return user ? JSON.parse(user) : null;
};
export const isAdmin = () => {
  const user = getUser();
  return user ? (user.role === 'admin' || !!user.is_admin) : false;
};

// ─────────────────────────────────────────────────
// Firebase Authentication Functions (lazy-loaded)
// ─────────────────────────────────────────────────

// Helper to lazily load Firebase modules only when needed.
// This prevents Firebase initialization from breaking basic auth.
const getFirebaseAuth = async () => {
  const { auth } = await import('./firebase');
  return auth;
};

const getFirebaseProviders = async () => {
  const { googleProvider, microsoftProvider } = await import('./firebase');
  return { googleProvider, microsoftProvider };
};

/**
 * Sign in with email and password via Firebase Auth.
 */
export const firebaseEmailLogin = async (email, password) => {
  const { signInWithEmailAndPassword } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  const firebaseUser = userCredential.user;
  const idToken = await firebaseUser.getIdToken();

  setToken(idToken);
  setUser({
    uid: firebaseUser.uid,
    username: firebaseUser.displayName || email.split('@')[0],
    full_name: firebaseUser.displayName || email.split('@')[0],
    email: firebaseUser.email,
    role: 'faculty',
    is_admin: false,
  });

  return firebaseUser;
};

/**
 * Register a new account with email and password via Firebase Auth.
 */
export const firebaseEmailRegister = async (email, password, displayName) => {
  const { createUserWithEmailAndPassword, updateProfile } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  const firebaseUser = userCredential.user;

  if (displayName) {
    await updateProfile(firebaseUser, { displayName });
  }

  const idToken = await firebaseUser.getIdToken();

  setToken(idToken);
  setUser({
    uid: firebaseUser.uid,
    username: displayName || email.split('@')[0],
    full_name: displayName || email.split('@')[0],
    email: firebaseUser.email,
    role: 'admin',
    is_admin: true,
  });

  return firebaseUser;
};

/**
 * Sign in with Google via popup.
 */
export const firebaseGoogleLogin = async () => {
  const { signInWithPopup } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  const { googleProvider } = await getFirebaseProviders();
  const result = await signInWithPopup(auth, googleProvider);
  const firebaseUser = result.user;
  const idToken = await firebaseUser.getIdToken();

  setToken(idToken);
  setUser({
    uid: firebaseUser.uid,
    username: firebaseUser.displayName || firebaseUser.email.split('@')[0],
    full_name: firebaseUser.displayName || '',
    email: firebaseUser.email,
    photo: firebaseUser.photoURL || '',
    role: 'faculty',
    is_admin: false,
  });

  return firebaseUser;
};

/**
 * Sign in with Microsoft via popup.
 */
export const firebaseMicrosoftLogin = async () => {
  const { signInWithPopup } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  const { microsoftProvider } = await getFirebaseProviders();
  const result = await signInWithPopup(auth, microsoftProvider);
  const firebaseUser = result.user;
  const idToken = await firebaseUser.getIdToken();

  setToken(idToken);
  setUser({
    uid: firebaseUser.uid,
    username: firebaseUser.displayName || firebaseUser.email.split('@')[0],
    full_name: firebaseUser.displayName || '',
    email: firebaseUser.email,
    photo: firebaseUser.photoURL || '',
    role: 'faculty',
    is_admin: false,
  });

  return firebaseUser;
};

/**
 * Sign out from Firebase and clear local storage.
 */
export const firebaseLogout = async () => {
  try {
    const { signOut } = await import('firebase/auth');
    const auth = await getFirebaseAuth();
    await signOut(auth);
  } catch (e) {
    // Ignore Firebase errors during logout
  }
  removeToken();
};

/**
 * Send a password reset email via Firebase.
 */
export const firebaseResetPassword = async (email) => {
  const { sendPasswordResetEmail } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  await sendPasswordResetEmail(auth, email);
};

/**
 * Subscribe to Firebase auth state changes.
 * Returns an unsubscribe function.
 */
export const onFirebaseAuthChange = async (callback) => {
  const { onAuthStateChanged } = await import('firebase/auth');
  const auth = await getFirebaseAuth();
  return onAuthStateChanged(auth, async (firebaseUser) => {
    if (firebaseUser) {
      const idToken = await firebaseUser.getIdToken();
      setToken(idToken);
      callback(firebaseUser);
    } else {
      callback(null);
    }
  });
};
