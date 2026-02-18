'use client';

import { Step, ThreadItem } from '@/lib/types';
import { Badge, cn } from '@/components/ui';
import {
    IconAtom,
    IconCheck,
    IconChevronDown,
    IconChevronRight,
    IconLoader2,
    IconX,
} from '@tabler/icons-react';
import { memo, useState } from 'react';

type ResearchStepsProps = {
    steps: Step[];
    threadItem: ThreadItem;
    /** When 'drawer', only the steps list is rendered (for the right-side pane). */
    variant?: 'inline' | 'drawer';
};

/**
 * Collapsible "Agent Reasoning" panel that shows:
 * - Planner steps (sub-query generation)
 * - Worker progress (source retrieval)
 * - Critique iterations with scores
 */
export const ResearchSteps = memo(
    ({ steps, threadItem, variant = 'inline' }: ResearchStepsProps) => {
        const [isExpanded, setIsExpanded] = useState(false);

        const isStopped = threadItem.status === 'ABORTED' || threadItem.status === 'ERROR';
        const isLoading = steps.some(step => step.status === 'PENDING') && !isStopped;
        const completedCount = steps.filter(s => s.status === 'COMPLETED').length;

        if (steps.length === 0) return null;

        const stepsList = (
            <div className="flex flex-col gap-2">
                {steps.map((step, index) => (
                    <ResearchStepItem key={step.id || index} step={step} />
                ))}
            </div>
        );

        if (variant === 'drawer') {
            return <div className="w-full px-1">{stepsList}</div>;
        }

        return (
            <div className="w-full">
                <button
                    className="bg-background shadow-subtle-xs hover:bg-secondary flex w-full cursor-pointer flex-row items-center gap-2 rounded-lg px-3 py-2.5 transition-colors"
                    onClick={() => setIsExpanded(!isExpanded)}
                >
                    <div className="mt-0.5">
                        {isLoading ? (
                            <IconLoader2
                                size={16}
                                strokeWidth={2}
                                className="text-muted-foreground animate-spin"
                            />
                        ) : (
                            <IconAtom
                                size={16}
                                strokeWidth={2}
                                className="text-muted-foreground"
                            />
                        )}
                    </div>
                    <div className="flex flex-col items-start">
                        <p className="text-sm font-medium">Agent Reasoning</p>
                    </div>
                    <div className="flex-1" />
                    <Badge variant="default" size="sm">
                        {completedCount}/{steps.length} Steps
                    </Badge>
                    {isExpanded ? (
                        <IconChevronDown size={14} strokeWidth={2} />
                    ) : (
                        <IconChevronRight size={14} strokeWidth={2} />
                    )}
                </button>

                {isExpanded && (
                    <div className="border-border/50 mt-1 rounded-lg border p-3">
                        {stepsList}
                    </div>
                )}
            </div>
        );
    }
);

ResearchSteps.displayName = 'ResearchSteps';

/** Show step detail as readable text; never dump raw JSON. */
function formatStepData(data: unknown): string {
    if (data == null) return '—';
    if (typeof data === 'string') return data;
    if (typeof data !== 'object') return String(data);
    const obj = data as Record<string, unknown>;
    const text =
        typeof obj.data === 'string'
            ? obj.data
            : typeof obj.text === 'string'
              ? obj.text
              : typeof obj.message === 'string'
                ? obj.message
                : typeof obj.description === 'string'
                  ? obj.description
                  : null;
    return text ?? 'Step completed';
}

const ResearchStepItem = ({ step }: { step: Step }) => {
    const [showSubSteps, setShowSubSteps] = useState(false);
    const subSteps = step.steps ? Object.values(step.steps) : [];

    return (
        <div className="flex flex-col gap-1">
            <div
                className={cn(
                    'flex flex-row items-start gap-2 rounded-md px-2 py-1.5',
                    subSteps.length > 0 && 'cursor-pointer hover:bg-secondary/50'
                )}
                onClick={() => subSteps.length > 0 && setShowSubSteps(!showSubSteps)}
            >
                <div className="mt-0.5">
                    <StepStatusIcon status={step.status} />
                </div>
                <p className="text-muted-foreground flex-1 text-sm">{step.text}</p>
                {subSteps.length > 0 && (
                    <span className="text-muted-foreground/50 text-xs">
                        {subSteps.length} detail{subSteps.length > 1 ? 's' : ''}
                    </span>
                )}
            </div>
            {showSubSteps && subSteps.length > 0 && (
                <div className="border-border/30 ml-6 flex flex-col gap-1 border-l pl-3">
                    {subSteps.map((sub, idx) => (
                        <div key={idx} className="flex flex-row items-center gap-2">
                            <StepStatusIcon status={sub.status} />
                            <p className="text-muted-foreground/70 text-xs">
                                {formatStepData(sub.data)}
                            </p>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

const StepStatusIcon = ({ status }: { status: string }) => {
    switch (status) {
        case 'COMPLETED':
            return <IconCheck size={14} strokeWidth={2} className="text-green-500" />;
        case 'PENDING':
            return (
                <IconLoader2
                    size={14}
                    strokeWidth={2}
                    className="text-muted-foreground animate-spin"
                />
            );
        case 'ERROR':
            return <IconX size={14} strokeWidth={2} className="text-red-500" />;
        default:
            return (
                <div className="bg-muted-foreground/30 h-2.5 w-2.5 rounded-full" />
            );
    }
};
