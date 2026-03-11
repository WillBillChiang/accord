'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/lib/auth';

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/negotiations/new', label: 'New Negotiation' },
  { href: '/attestation', label: 'Attestation' },
  { href: '/admin', label: 'Admin' },
];

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, signOut, isMfaEnrolled } = useAuth();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login');
    }
  }, [isLoading, user, router]);

  useEffect(() => {
    if (!isLoading && user && !isMfaEnrolled()) {
      router.replace('/mfa-setup');
    }
  }, [isLoading, user, isMfaEnrolled, router]);

  const handleSignOut = async () => {
    await signOut();
    router.push('/login');
  };

  // Show nothing while checking auth state
  if (isLoading || !user) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <nav className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 flex items-center h-16">
          <Link
            href="/dashboard"
            className="text-xl font-bold text-white mr-10"
          >
            Accord
          </Link>
          <div className="flex gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                  pathname.startsWith(item.href)
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="ml-auto">
            <button
              onClick={handleSignOut}
              className="text-gray-400 hover:text-white text-sm"
            >
              Sign Out
            </button>
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
