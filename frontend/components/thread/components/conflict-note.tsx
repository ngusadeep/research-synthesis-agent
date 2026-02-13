'use client';

import { Alert, AlertDescription, Badge, cn } from '@/components/ui';
import { IconAlertTriangle, IconArrowsExchange } from '@tabler/icons-react';
import { memo, useState } from 'react';

export type ConflictData = {
    claim_a: string;
    source_a: string;
    claim_b: string;
    source_b: string;
    description: string;
    resolution?: string;
};

/**
 * Highlighted conflict annotation within the research report.
 *
 * Shows contradictions between sources with expandable details.
 */
export const ConflictNote = memo(({ conflict }: { conflict: ConflictData }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    return (
        <Alert
            variant="warning"
            className="cursor-pointer"
            onClick={() => setIsExpanded(!isExpanded)}
        >
            <AlertDescription>
                <div className="flex flex-col gap-2">
                    <div className="flex flex-row items-center gap-2">
                        <IconAlertTriangle size={14} strokeWidth={2} className="text-yellow-600 shrink-0" />
                        <p className="text-sm font-medium">Conflicting Information</p>
                        <div className="flex-1" />
                        <Badge variant="secondary" size="sm" className="text-[10px]">
                            Conflict
                        </Badge>
                    </div>
                    <p className="text-muted-foreground text-xs">{conflict.description}</p>

                    {isExpanded && (
                        <div className="mt-2 flex flex-col gap-3">
                            <div className="border-border/50 flex flex-col gap-1 rounded-md border p-2">
                                <p className="text-xs font-medium">Source A</p>
                                <p className="text-muted-foreground text-xs italic">
                                    &ldquo;{conflict.claim_a}&rdquo;
                                </p>
                                <p className="text-muted-foreground/60 text-[10px]">
                                    {conflict.source_a}
                                </p>
                            </div>

                            <div className="flex items-center justify-center">
                                <IconArrowsExchange
                                    size={16}
                                    strokeWidth={2}
                                    className="text-yellow-500"
                                />
                            </div>

                            <div className="border-border/50 flex flex-col gap-1 rounded-md border p-2">
                                <p className="text-xs font-medium">Source B</p>
                                <p className="text-muted-foreground text-xs italic">
                                    &ldquo;{conflict.claim_b}&rdquo;
                                </p>
                                <p className="text-muted-foreground/60 text-[10px]">
                                    {conflict.source_b}
                                </p>
                            </div>

                            {conflict.resolution && (
                                <div className="bg-secondary/50 rounded-md p-2">
                                    <p className="text-xs font-medium">Resolution</p>
                                    <p className="text-muted-foreground text-xs">
                                        {conflict.resolution}
                                    </p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </AlertDescription>
        </Alert>
    );
});

ConflictNote.displayName = 'ConflictNote';

/**
 * List of all detected conflicts in a research report.
 */
export const ConflictNoteList = ({ conflicts }: { conflicts: ConflictData[] }) => {
    if (!conflicts || conflicts.length === 0) return null;

    return (
        <div className="flex w-full flex-col gap-2">
            <p className="text-muted-foreground text-xs font-medium">
                {conflicts.length} Conflict{conflicts.length > 1 ? 's' : ''} Detected
            </p>
            {conflicts.map((conflict, index) => (
                <ConflictNote key={index} conflict={conflict} />
            ))}
        </div>
    );
};
