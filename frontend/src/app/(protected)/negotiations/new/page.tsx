'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import {
  NegotiationRole,
  DisclosureTier,
  type PartyConfig,
} from '@/types/negotiation';

const STEPS = [
  'Role Selection',
  'Hard Constraints',
  'Disclosure Policy',
  'Strategy',
  'Review & Create',
];

export default function NewNegotiationPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Session info
  const [description, setDescription] = useState('');
  const [useCase, setUseCase] = useState('');

  // Step 1: Role
  const [role, setRole] = useState<NegotiationRole>(NegotiationRole.BUYER);

  // Step 2: Hard constraints
  const [budgetCap, setBudgetCap] = useState<number>(100000);
  const [reservationPrice, setReservationPrice] = useState<number>(50000);
  const [maxRounds, setMaxRounds] = useState<number>(10);
  const [maxConcession, setMaxConcession] = useState<number>(5);

  // Step 3: Disclosure policy
  const [disclosureFields, setDisclosureFields] = useState<
    Record<string, DisclosureTier>
  >({});
  const [newFieldName, setNewFieldName] = useState('');
  const [newFieldTier, setNewFieldTier] = useState<DisclosureTier>(
    DisclosureTier.MAY_DISCLOSE
  );

  // Step 4: Strategy
  const [strategyNotes, setStrategyNotes] = useState('');
  const [priorityIssues, setPriorityIssues] = useState<string[]>([]);
  const [newPriority, setNewPriority] = useState('');
  const [dealStructures, setDealStructures] = useState<string[]>([]);
  const [newStructure, setNewStructure] = useState('');

  const addDisclosureField = () => {
    if (newFieldName.trim()) {
      setDisclosureFields((prev) => ({
        ...prev,
        [newFieldName.trim()]: newFieldTier,
      }));
      setNewFieldName('');
    }
  };

  const removeDisclosureField = (key: string) => {
    setDisclosureFields((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const addPriority = () => {
    if (newPriority.trim()) {
      setPriorityIssues((prev) => [...prev, newPriority.trim()]);
      setNewPriority('');
    }
  };

  const removePriority = (index: number) => {
    setPriorityIssues((prev) => prev.filter((_, i) => i !== index));
  };

  const addStructure = () => {
    if (newStructure.trim()) {
      setDealStructures((prev) => [...prev, newStructure.trim()]);
      setNewStructure('');
    }
  };

  const removeStructure = (index: number) => {
    setDealStructures((prev) => prev.filter((_, i) => i !== index));
  };

  const canProceed = () => {
    switch (currentStep) {
      case 0:
        return true;
      case 1:
        return budgetCap > 0 && reservationPrice > 0 && maxRounds > 0;
      case 2:
        return true;
      case 3:
        return true;
      case 4:
        return true;
      default:
        return false;
    }
  };

  const handleCreate = async () => {
    setLoading(true);
    setError('');
    try {
      const sessionResult = await apiClient.createSession({
        description: description || undefined,
        use_case: useCase || undefined,
      });

      const config: PartyConfig = {
        role,
        budget_cap: budgetCap,
        reservation_price: reservationPrice,
        max_rounds: maxRounds,
        max_concession_per_round: maxConcession,
        disclosure_fields: disclosureFields,
        strategy_notes: strategyNotes,
        priority_issues: priorityIssues,
        acceptable_deal_structures: dealStructures,
      };

      await apiClient.onboardParty(sessionResult.session_id, {
        role,
        config,
      });

      router.push(`/negotiations/${sessionResult.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session');
    } finally {
      setLoading(false);
    }
  };

  const tierLabel = (tier: DisclosureTier) => {
    switch (tier) {
      case DisclosureTier.MUST_DISCLOSE:
        return 'Must Disclose';
      case DisclosureTier.MAY_DISCLOSE:
        return 'May Disclose';
      case DisclosureTier.NEVER_DISCLOSE:
        return 'Never Disclose';
    }
  };

  const tierColor = (tier: DisclosureTier) => {
    switch (tier) {
      case DisclosureTier.MUST_DISCLOSE:
        return 'bg-green-900 text-green-300';
      case DisclosureTier.MAY_DISCLOSE:
        return 'bg-yellow-900 text-yellow-300';
      case DisclosureTier.NEVER_DISCLOSE:
        return 'bg-red-900 text-red-300';
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-8">New Negotiation</h1>

      {/* Progress indicator */}
      <div className="flex items-center mb-10">
        {STEPS.map((step, index) => (
          <div key={step} className="flex items-center flex-1">
            <div className="flex flex-col items-center flex-1">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  index <= currentStep
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-500'
                }`}
              >
                {index + 1}
              </div>
              <span
                className={`text-xs mt-1 ${
                  index <= currentStep ? 'text-gray-300' : 'text-gray-600'
                }`}
              >
                {step}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <div
                className={`h-px flex-1 mx-2 ${
                  index < currentStep ? 'bg-blue-600' : 'bg-gray-800'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-6 p-3 bg-red-900/50 border border-red-700 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-900 rounded-xl p-8 border border-gray-800">
        {/* Step 0: Role Selection */}
        {currentStep === 0 && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">
              Select Your Role
            </h2>
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Session Description
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Enterprise software license negotiation"
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Use Case
              </label>
              <input
                type="text"
                value={useCase}
                onChange={(e) => setUseCase(e.target.value)}
                placeholder="e.g. SaaS licensing, M&A, procurement"
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setRole(NegotiationRole.BUYER)}
                className={`p-6 rounded-xl border-2 text-left transition ${
                  role === NegotiationRole.BUYER
                    ? 'border-blue-500 bg-blue-950/30'
                    : 'border-gray-700 hover:border-gray-600'
                }`}
              >
                <h3 className="text-white font-semibold mb-1">Buyer</h3>
                <p className="text-gray-400 text-sm">
                  You want to purchase goods, services, or assets
                </p>
              </button>
              <button
                type="button"
                onClick={() => setRole(NegotiationRole.SELLER)}
                className={`p-6 rounded-xl border-2 text-left transition ${
                  role === NegotiationRole.SELLER
                    ? 'border-blue-500 bg-blue-950/30'
                    : 'border-gray-700 hover:border-gray-600'
                }`}
              >
                <h3 className="text-white font-semibold mb-1">Seller</h3>
                <p className="text-gray-400 text-sm">
                  You want to sell goods, services, or assets
                </p>
              </button>
            </div>
          </div>
        )}

        {/* Step 1: Hard Constraints */}
        {currentStep === 1 && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">
              Hard Constraints
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              These constraints cannot be exceeded during negotiation. Your AI
              agent will strictly respect these limits.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Budget Cap ($)
                </label>
                <input
                  type="number"
                  value={budgetCap}
                  onChange={(e) => setBudgetCap(Number(e.target.value))}
                  min={0}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Reservation Price ($)
                </label>
                <input
                  type="number"
                  value={reservationPrice}
                  onChange={(e) => setReservationPrice(Number(e.target.value))}
                  min={0}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  {role === NegotiationRole.BUYER
                    ? 'Maximum you will pay'
                    : 'Minimum you will accept'}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Max Rounds
                </label>
                <input
                  type="number"
                  value={maxRounds}
                  onChange={(e) => setMaxRounds(Number(e.target.value))}
                  min={1}
                  max={50}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Max Concession Per Round (%)
                </label>
                <input
                  type="number"
                  value={maxConcession}
                  onChange={(e) => setMaxConcession(Number(e.target.value))}
                  min={0}
                  max={100}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Disclosure Policy */}
        {currentStep === 2 && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">
              Disclosure Policy
            </h2>
            <p className="text-gray-400 text-sm mb-6">
              Control what information your AI agent may reveal during
              negotiation. Each field gets a tier: Must Disclose (always share),
              May Disclose (agent decides), or Never Disclose (kept secret).
            </p>

            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newFieldName}
                onChange={(e) => setNewFieldName(e.target.value)}
                placeholder="Field name (e.g. annual_revenue)"
                className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                onKeyDown={(e) => e.key === 'Enter' && addDisclosureField()}
              />
              <select
                value={newFieldTier}
                onChange={(e) =>
                  setNewFieldTier(e.target.value as DisclosureTier)
                }
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              >
                <option value={DisclosureTier.MUST_DISCLOSE}>
                  Must Disclose
                </option>
                <option value={DisclosureTier.MAY_DISCLOSE}>
                  May Disclose
                </option>
                <option value={DisclosureTier.NEVER_DISCLOSE}>
                  Never Disclose
                </option>
              </select>
              <button
                type="button"
                onClick={addDisclosureField}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
              >
                Add
              </button>
            </div>

            {Object.keys(disclosureFields).length === 0 ? (
              <p className="text-gray-500 text-sm py-4">
                No disclosure fields added yet. Add fields to control what
                information is shared.
              </p>
            ) : (
              <div className="space-y-2">
                {Object.entries(disclosureFields).map(([key, tier]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between bg-gray-800 rounded-lg p-3"
                  >
                    <span className="text-white text-sm">{key}</span>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${tierColor(tier)}`}
                      >
                        {tierLabel(tier)}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeDisclosureField(key)}
                        className="text-gray-500 hover:text-red-400 text-sm"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 3: Strategy */}
        {currentStep === 3 && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-4">
              Strategy Configuration
            </h2>
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Strategy Notes
              </label>
              <textarea
                value={strategyNotes}
                onChange={(e) => setStrategyNotes(e.target.value)}
                rows={4}
                placeholder="Provide guidance for your AI agent's negotiation strategy..."
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 resize-none"
              />
            </div>

            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Priority Issues
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value)}
                  placeholder="e.g. Price, Delivery timeline, SLA"
                  className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  onKeyDown={(e) => e.key === 'Enter' && addPriority()}
                />
                <button
                  type="button"
                  onClick={addPriority}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {priorityIssues.map((issue, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-gray-800 rounded-full text-sm text-gray-300"
                  >
                    {issue}
                    <button
                      type="button"
                      onClick={() => removePriority(index)}
                      className="text-gray-500 hover:text-red-400 ml-1"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Acceptable Deal Structures
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newStructure}
                  onChange={(e) => setNewStructure(e.target.value)}
                  placeholder="e.g. Lump sum, Installments, Revenue share"
                  className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  onKeyDown={(e) => e.key === 'Enter' && addStructure()}
                />
                <button
                  type="button"
                  onClick={addStructure}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {dealStructures.map((structure, index) => (
                  <span
                    key={index}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-gray-800 rounded-full text-sm text-gray-300"
                  >
                    {structure}
                    <button
                      type="button"
                      onClick={() => removeStructure(index)}
                      className="text-gray-500 hover:text-red-400 ml-1"
                    >
                      x
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Review */}
        {currentStep === 4 && (
          <div>
            <h2 className="text-lg font-semibold text-white mb-6">
              Review Configuration
            </h2>
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Session
                </h3>
                <div className="bg-gray-800 rounded-lg p-4 space-y-1">
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Description:</span>{' '}
                    {description || 'Not set'}
                  </p>
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Use Case:</span>{' '}
                    {useCase || 'Not set'}
                  </p>
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Role:</span>{' '}
                    {role === NegotiationRole.BUYER ? 'Buyer' : 'Seller'}
                  </p>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Hard Constraints
                </h3>
                <div className="bg-gray-800 rounded-lg p-4 grid grid-cols-2 gap-2">
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Budget Cap:</span> $
                    {budgetCap.toLocaleString()}
                  </p>
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Reservation Price:</span> $
                    {reservationPrice.toLocaleString()}
                  </p>
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Max Rounds:</span>{' '}
                    {maxRounds}
                  </p>
                  <p className="text-white text-sm">
                    <span className="text-gray-400">Max Concession:</span>{' '}
                    {maxConcession}%
                  </p>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Disclosure Fields ({Object.keys(disclosureFields).length})
                </h3>
                {Object.keys(disclosureFields).length > 0 ? (
                  <div className="bg-gray-800 rounded-lg p-4 space-y-1">
                    {Object.entries(disclosureFields).map(([key, tier]) => (
                      <p key={key} className="text-white text-sm">
                        <span className="text-gray-400">{key}:</span>{' '}
                        <span
                          className={`px-2 py-0.5 rounded text-xs ${tierColor(tier)}`}
                        >
                          {tierLabel(tier)}
                        </span>
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">
                    No disclosure fields configured
                  </p>
                )}
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-2">
                  Strategy
                </h3>
                <div className="bg-gray-800 rounded-lg p-4 space-y-2">
                  <p className="text-white text-sm">
                    {strategyNotes || 'No strategy notes'}
                  </p>
                  {priorityIssues.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      <span className="text-gray-400 text-sm">
                        Priorities:
                      </span>
                      {priorityIssues.map((issue, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300"
                        >
                          {issue}
                        </span>
                      ))}
                    </div>
                  )}
                  {dealStructures.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      <span className="text-gray-400 text-sm">
                        Structures:
                      </span>
                      {dealStructures.map((s, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-gray-700 rounded text-xs text-gray-300"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Navigation buttons */}
        <div className="flex justify-between mt-8 pt-6 border-t border-gray-800">
          <button
            type="button"
            onClick={() => setCurrentStep((prev) => Math.max(0, prev - 1))}
            disabled={currentStep === 0}
            className="px-4 py-2 text-gray-400 hover:text-white disabled:opacity-30 transition"
          >
            Back
          </button>
          {currentStep < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() =>
                setCurrentStep((prev) => Math.min(STEPS.length - 1, prev + 1))
              }
              disabled={!canProceed()}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 transition"
            >
              Next
            </button>
          ) : (
            <button
              type="button"
              onClick={handleCreate}
              disabled={loading}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 transition"
            >
              {loading ? 'Creating...' : 'Create & Start'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
