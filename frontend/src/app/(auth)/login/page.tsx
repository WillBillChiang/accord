'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

export default function LoginPage() {
  const router = useRouter();
  const { signIn, mfaRequired, isMfaEnrolled, user } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Redirect to MFA challenge page when MFA is required during sign-in
  useEffect(() => {
    if (mfaRequired) {
      router.push('/login/mfa');
    }
  }, [mfaRequired, router]);

  // After successful sign-in (user is set), check MFA enrollment
  useEffect(() => {
    if (user && !mfaRequired) {
      if (!isMfaEnrolled()) {
        router.push('/mfa-setup');
      } else {
        router.push('/dashboard');
      }
    }
  }, [user, mfaRequired, isMfaEnrolled, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await signIn(email, password);
      // Navigation is handled by the useEffect hooks above
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md">
      <h1 className="text-3xl font-bold text-white text-center mb-8">
        Sign In to Accord
      </h1>
      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 rounded-xl p-8 border border-gray-800"
      >
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}
        <div className="mb-4">
          <label
            htmlFor="email"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <div className="mb-6">
          <label
            htmlFor="password"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 disabled:opacity-50 transition"
        >
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
        <p className="mt-4 text-center text-gray-400 text-sm">
          Don&apos;t have an account?{' '}
          <Link href="/signup" className="text-blue-400 hover:underline">
            Sign up
          </Link>
        </p>
      </form>
    </div>
  );
}
