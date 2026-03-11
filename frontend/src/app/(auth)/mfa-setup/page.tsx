'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  multiFactor,
  TotpMultiFactorGenerator,
  TotpSecret,
} from 'firebase/auth';
import { useAuth } from '@/lib/auth';

export default function MfaSetupPage() {
  const router = useRouter();
  const { firebaseUser } = useAuth();
  const [totpSecret, setTotpSecret] = useState<TotpSecret | null>(null);
  const [qrUrl, setQrUrl] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'generate' | 'verify'>('generate');

  const handleGenerateSecret = async () => {
    if (!firebaseUser) {
      setError('You must be signed in to set up MFA.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const multiFactorSession = await multiFactor(firebaseUser).getSession();
      const secret = await TotpMultiFactorGenerator.generateSecret(multiFactorSession);
      setTotpSecret(secret);
      const url = secret.generateQrCodeUrl(
        firebaseUser.email || 'user',
        'Accord'
      );
      setQrUrl(url);
      setStep('verify');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate MFA secret');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firebaseUser || !totpSecret) {
      setError('Missing authentication data. Please try again.');
      return;
    }
    if (!/^\d{6}$/.test(verificationCode)) {
      setError('Please enter a valid 6-digit code.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const assertion = TotpMultiFactorGenerator.assertionForEnrollment(
        totpSecret,
        verificationCode
      );
      await multiFactor(firebaseUser).enroll(assertion, 'Accord TOTP');
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
        Set Up Two-Factor Authentication
      </h1>
      <p className="text-gray-400 text-center mb-8 text-sm">
        Accord requires TOTP-based two-factor authentication for all accounts.
      </p>

      <div className="bg-gray-900 rounded-xl p-8 border border-gray-800">
        {error && (
          <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {step === 'generate' && (
          <div className="text-center">
            <p className="text-gray-300 mb-6 text-sm">
              You will need an authenticator app such as Google Authenticator or Authy
              to complete this setup.
            </p>
            <button
              onClick={handleGenerateSecret}
              disabled={loading}
              className="w-full py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {loading ? 'Generating...' : 'Generate Secret Key'}
            </button>
          </div>
        )}

        {step === 'verify' && (
          <form onSubmit={handleVerify}>
            <div className="mb-6">
              <p className="text-gray-300 text-sm mb-3">
                Scan this QR code with your authenticator app:
              </p>
              <div className="bg-white p-4 rounded-lg flex items-center justify-center">
                {/*
                  The QR code URL can be rendered by an <img> tag pointing to
                  a QR code generation service, or by a client-side QR library.
                  For security, we display the otpauth:// URI so users can also
                  enter it manually.
                */}
                <img
                  src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUrl)}`}
                  alt="TOTP QR Code"
                  width={200}
                  height={200}
                />
              </div>
              <details className="mt-3">
                <summary className="text-gray-400 text-xs cursor-pointer hover:text-gray-300">
                  Cannot scan? Show manual entry URI
                </summary>
                <p className="mt-2 text-xs text-gray-500 break-all font-mono bg-gray-800 p-2 rounded">
                  {qrUrl}
                </p>
              </details>
            </div>

            <div className="mb-6">
              <label
                htmlFor="verificationCode"
                className="block text-sm font-medium text-gray-300 mb-1"
              >
                Enter the 6-digit code from your app
              </label>
              <input
                id="verificationCode"
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                required
                autoComplete="one-time-code"
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-center text-2xl tracking-widest focus:outline-none focus:border-blue-500"
                placeholder="000000"
              />
            </div>

            <button
              type="submit"
              disabled={loading || verificationCode.length !== 6}
              className="w-full py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {loading ? 'Verifying...' : 'Verify & Enable MFA'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
