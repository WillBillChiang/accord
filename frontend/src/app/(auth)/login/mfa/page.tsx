'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { TotpMultiFactorGenerator } from 'firebase/auth';
import { useAuth } from '@/lib/auth';

export default function MfaChallengePage() {
  const router = useRouter();
  const { mfaResolver, mfaRequired } = useAuth();
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // If no MFA challenge is pending, redirect to login
  if (!mfaRequired || !mfaResolver) {
    if (typeof window !== 'undefined') {
      router.replace('/login');
    }
    return (
      <div className="w-full max-w-md text-center">
        <p className="text-gray-400">Redirecting to login...</p>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setError('Please enter a valid 6-digit code.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      // Find the TOTP hint among enrolled factors
      const totpHint = mfaResolver.hints.find(
        (hint) => hint.factorId === TotpMultiFactorGenerator.FACTOR_ID
      );

      if (!totpHint) {
        setError('No TOTP factor found. Please contact support.');
        setLoading(false);
        return;
      }

      const assertion = TotpMultiFactorGenerator.assertionForSignIn(
        totpHint.uid,
        code
      );
      await mfaResolver.resolveSignIn(assertion);
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'MFA verification failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md">
      <h1 className="text-3xl font-bold text-white text-center mb-4">
        Two-Factor Authentication
      </h1>
      <p className="text-gray-400 text-center mb-8 text-sm">
        Enter the 6-digit code from your authenticator app to continue.
      </p>

      <form
        onSubmit={handleSubmit}
        className="bg-gray-900 rounded-xl p-8 border border-gray-800"
      >
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        <div className="mb-6">
          <label
            htmlFor="mfaCode"
            className="block text-sm font-medium text-gray-300 mb-1"
          >
            Authentication Code
          </label>
          <input
            id="mfaCode"
            type="text"
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            required
            autoComplete="one-time-code"
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-center text-2xl tracking-widest focus:outline-none focus:border-blue-500"
            placeholder="000000"
          />
        </div>

        <button
          type="submit"
          disabled={loading || code.length !== 6}
          className="w-full py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 disabled:opacity-50 transition"
        >
          {loading ? 'Verifying...' : 'Verify'}
        </button>
      </form>
    </div>
  );
}
