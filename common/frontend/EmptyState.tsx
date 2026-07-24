/**
 * common/frontend/EmptyState.tsx
 * ────────────────────────────────
 * Shared empty-state placeholder component used by all Velocity AI apps.
 *
 * Usage:
 *
 *   import EmptyState from '../../../common/frontend/EmptyState';
 *
 *   <EmptyState
 *     icon="📄"
 *     title="No Report Yet"
 *     description="Upload a drawing and run analysis first."
 *   />
 */

import React from 'react';

interface EmptyStateProps {
  /** Large emoji or icon character displayed above the title */
  icon: string;
  /** Bold heading */
  title: string;
  /** Descriptive paragraph below the heading */
  description: string;
  /** Optional extra content (e.g. a CTA button) rendered below description */
  children?: React.ReactNode;
}

/**
 * Centred placeholder shown when a panel has no content yet.
 * Relies on the `.empty-state` CSS class defined in common/frontend/styles.css.
 */
export default function EmptyState({
  icon,
  title,
  description,
  children,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="icon" role="img" aria-hidden="true">
        {icon}
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {children}
    </div>
  );
}
