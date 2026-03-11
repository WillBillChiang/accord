'use client';

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  createElement,
  type ReactNode,
} from 'react';
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  multiFactor,
  type User,
  type MultiFactorResolver,
  type MultiFactorError,
} from 'firebase/auth';
import { auth } from './firebase';

export interface AuthUser {
  userId: string;
  email: string;
  groups: string[];
}

export interface AuthContextType {
  user: AuthUser | null;
  firebaseUser: User | null;
  isLoading: boolean;
  mfaRequired: boolean;
  mfaResolver: MultiFactorResolver | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  isAdmin: () => Promise<boolean>;
  isMfaEnrolled: () => boolean;
}

export const AuthContext = createContext<AuthContextType>({
  user: null,
  firebaseUser: null,
  isLoading: true,
  mfaRequired: false,
  mfaResolver: null,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  getToken: async () => null,
  isAdmin: async () => false,
  isMfaEnrolled: () => false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [mfaResolver, setMfaResolver] = useState<MultiFactorResolver | null>(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (fbUser) => {
      if (fbUser) {
        setFirebaseUser(fbUser);
        setUser({
          userId: fbUser.uid,
          email: fbUser.email || '',
          groups: [],
        });
      } else {
        setFirebaseUser(null);
        setUser(null);
      }
      setIsLoading(false);
    });

    return () => unsubscribe();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    setMfaRequired(false);
    setMfaResolver(null);
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (error: unknown) {
      const firebaseError = error as { code?: string; customData?: { _serverResponse?: unknown } };
      if (firebaseError.code === 'auth/multi-factor-auth-required') {
        const mfaError = error as MultiFactorError;
        const { getMultiFactorResolver } = await import('firebase/auth');
        const resolver = getMultiFactorResolver(auth, mfaError);
        setMfaResolver(resolver);
        setMfaRequired(true);
        return;
      }
      throw error;
    }
  }, []);

  const signUp = useCallback(async (email: string, password: string, _name: string) => {
    await createUserWithEmailAndPassword(auth, email, password);
  }, []);

  const handleSignOut = useCallback(async () => {
    await firebaseSignOut(auth);
    setMfaRequired(false);
    setMfaResolver(null);
  }, []);

  const getToken = useCallback(async (): Promise<string | null> => {
    const currentUser = auth.currentUser;
    if (!currentUser) return null;
    return currentUser.getIdToken();
  }, []);

  const isAdmin = useCallback(async (): Promise<boolean> => {
    const currentUser = auth.currentUser;
    if (!currentUser) return false;
    const tokenResult = await currentUser.getIdTokenResult();
    return tokenResult.claims.admin === true;
  }, []);

  const isMfaEnrolled = useCallback((): boolean => {
    const currentUser = auth.currentUser;
    if (!currentUser) return false;
    return multiFactor(currentUser).enrolledFactors.length > 0;
  }, []);

  const value: AuthContextType = {
    user,
    firebaseUser,
    isLoading,
    mfaRequired,
    mfaResolver,
    signIn,
    signUp,
    signOut: handleSignOut,
    getToken,
    isAdmin,
    isMfaEnrolled,
  };

  return createElement(AuthContext.Provider, { value }, children);
}

export const useAuth = () => useContext(AuthContext);
