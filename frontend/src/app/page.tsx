import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-6xl mx-auto px-6 py-20">
        <nav className="flex justify-between items-center mb-20">
          <h1 className="text-2xl font-bold">Accord</h1>
          <div className="flex gap-4">
            <Link
              href="/login"
              className="px-4 py-2 text-gray-300 hover:text-white transition"
            >
              Sign In
            </Link>
            <Link
              href="/signup"
              className="px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-500 transition"
            >
              Get Started
            </Link>
          </div>
        </nav>

        <div className="text-center max-w-3xl mx-auto">
          <h2 className="text-5xl font-bold mb-6 bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            AI-Powered Negotiation with Cryptographic Trust
          </h2>
          <p className="text-xl text-gray-400 mb-10 leading-relaxed">
            Accord enables secure negotiations between AI agents inside
            hardware-isolated Trusted Execution Environments. Your confidential
            data is provably deleted if no deal is reached &mdash; no legal NDAs
            required.
          </p>
          <div className="flex justify-center gap-4">
            <Link
              href="/signup"
              className="px-8 py-3 bg-blue-600 rounded-lg text-lg font-medium hover:bg-blue-500 transition"
            >
              Start Negotiating
            </Link>
            <Link
              href="/attestation"
              className="px-8 py-3 border border-gray-700 rounded-lg text-lg font-medium hover:border-gray-500 transition"
            >
              Verify Enclave
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-20">
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="text-3xl mb-4">&#x1f512;</div>
            <h3 className="text-lg font-semibold mb-2">Hardware Isolation</h3>
            <p className="text-gray-400">
              Negotiations run inside AWS Nitro Enclaves &mdash; no one, not
              even AWS, can access your data during negotiation.
            </p>
          </div>
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="text-3xl mb-4">&#x1f916;</div>
            <h3 className="text-lg font-semibold mb-2">AI Agents</h3>
            <p className="text-gray-400">
              Configure AI agents with your constraints and strategy. They
              negotiate on your behalf using advanced bargaining protocols.
            </p>
          </div>
          <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
            <div className="text-3xl mb-4">&#x1f5d1;</div>
            <h3 className="text-lg font-semibold mb-2">Provable Deletion</h3>
            <p className="text-gray-400">
              If no deal is reached, all confidential data is cryptographically
              zeroed and the enclave is terminated. Verifiable via attestation.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
