'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export default function AttestationPage() {
  const [nonce, setNonce] = useState('');
  const [verifyPcr0, setVerifyPcr0] = useState('');
  const [verifyPcr1, setVerifyPcr1] = useState('');
  const [verifyPcr2, setVerifyPcr2] = useState('');

  const {
    data: attestation,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['attestation', nonce],
    queryFn: () => apiClient.getAttestation(nonce || undefined),
    enabled: false,
  });

  const verifyMutation = useMutation({
    mutationFn: () =>
      apiClient.verifyAttestation(
        verifyPcr0,
        verifyPcr1 || undefined,
        verifyPcr2 || undefined
      ),
  });

  const handleFetchAttestation = () => {
    refetch();
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-2">
        Enclave Attestation
      </h1>
      <p className="text-gray-400 mb-8">
        Verify the integrity of the TEE enclave by inspecting its attestation
        document and PCR values. This cryptographically proves the enclave is
        running the expected code.
      </p>

      {/* Fetch attestation */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Get Attestation Document
        </h2>
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={nonce}
            onChange={(e) => setNonce(e.target.value)}
            placeholder="Optional nonce (for freshness verification)"
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
          />
          <button
            onClick={handleFetchAttestation}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 transition"
          >
            {isLoading ? 'Fetching...' : 'Fetch'}
          </button>
        </div>

        {attestation && (
          <div className="space-y-3">
            <div className="bg-gray-800 rounded-lg p-4">
              <p className="text-xs font-medium text-gray-400 mb-1">
                PCR0 (Enclave Image)
              </p>
              <p className="text-sm text-green-400 font-mono break-all">
                {attestation.pcr0}
              </p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <p className="text-xs font-medium text-gray-400 mb-1">
                PCR1 (Boot Kernel)
              </p>
              <p className="text-sm text-green-400 font-mono break-all">
                {attestation.pcr1}
              </p>
            </div>
            <div className="bg-gray-800 rounded-lg p-4">
              <p className="text-xs font-medium text-gray-400 mb-1">
                PCR2 (Application)
              </p>
              <p className="text-sm text-green-400 font-mono break-all">
                {attestation.pcr2}
              </p>
            </div>
            <div className="flex gap-4 text-sm text-gray-400">
              <span>
                Timestamp:{' '}
                {new Date(attestation.timestamp * 1000).toLocaleString()}
              </span>
              {attestation.nonce && <span>Nonce: {attestation.nonce}</span>}
            </div>
          </div>
        )}
      </div>

      {/* Verify attestation */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">
          Verify Attestation
        </h2>
        <p className="text-gray-400 text-sm mb-4">
          Provide expected PCR values to verify the enclave is running the
          correct code. PCR0 is required; PCR1 and PCR2 are optional.
        </p>
        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Expected PCR0 (required)
            </label>
            <input
              type="text"
              value={verifyPcr0}
              onChange={(e) => setVerifyPcr0(e.target.value)}
              placeholder="Hex-encoded PCR0 value"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Expected PCR1 (optional)
            </label>
            <input
              type="text"
              value={verifyPcr1}
              onChange={(e) => setVerifyPcr1(e.target.value)}
              placeholder="Hex-encoded PCR1 value"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Expected PCR2 (optional)
            </label>
            <input
              type="text"
              value={verifyPcr2}
              onChange={(e) => setVerifyPcr2(e.target.value)}
              placeholder="Hex-encoded PCR2 value"
              className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>
        <button
          onClick={() => verifyMutation.mutate()}
          disabled={!verifyPcr0 || verifyMutation.isPending}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 transition"
        >
          {verifyMutation.isPending ? 'Verifying...' : 'Verify'}
        </button>

        {verifyMutation.isSuccess && (
          <div
            className={`mt-4 p-4 rounded-lg border ${
              verifyMutation.data.verified
                ? 'bg-green-950/20 border-green-800/30'
                : 'bg-red-950/20 border-red-800/30'
            }`}
          >
            <p
              className={`font-medium ${verifyMutation.data.verified ? 'text-green-400' : 'text-red-400'}`}
            >
              {verifyMutation.data.verified
                ? 'Attestation Verified - Enclave integrity confirmed'
                : 'Verification Failed - PCR values do not match'}
            </p>
          </div>
        )}

        {verifyMutation.isError && (
          <p className="text-red-400 text-sm mt-4">
            {verifyMutation.error instanceof Error
              ? verifyMutation.error.message
              : 'Verification request failed'}
          </p>
        )}
      </div>
    </div>
  );
}
