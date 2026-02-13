'use client';

import { Source } from '@/lib/types';
import { Badge, cn } from '@/components/ui';
import { IconExternalLink, IconShield } from '@tabler/icons-react';
import { memo } from 'react';

/**
 * Rich source display card with:
 * - Title and snippet
 * - Source type badge
 * - Credibility score indicator
 * - External link
 */
export const SourceCard = memo(
    ({
        source,
        credibilityScore,
        sourceType,
    }: {
        source: Source;
        credibilityScore?: number;
        sourceType?: string;
    }) => {
        const score = credibilityScore ?? 0.5;
        const scoreColor =
            score >= 0.75 ? 'text-green-500' : score >= 0.5 ? 'text-yellow-500' : 'text-red-500';
        const scoreLabel = score >= 0.75 ? 'High' : score >= 0.5 ? 'Medium' : 'Low';

        const hostname = (() => {
            try {
                return new URL(source.link).hostname.replace('www.', '');
            } catch {
                return source.link;
            }
        })();

        return (
            <a
                href={source.link}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-background shadow-subtle-xs hover:bg-secondary group flex flex-col gap-2 rounded-lg border border-transparent p-3 transition-all hover:border-border/50"
            >
                <div className="flex flex-row items-start gap-2">
                    <div className="flex flex-1 flex-col gap-1">
                        <p className="line-clamp-1 text-sm font-medium group-hover:underline">
                            {source.title}
                        </p>
                        <p className="text-muted-foreground/60 text-xs">{hostname}</p>
                    </div>
                    <IconExternalLink
                        size={14}
                        strokeWidth={2}
                        className="text-muted-foreground/50 mt-0.5 shrink-0 opacity-0 group-hover:opacity-100"
                    />
                </div>

                {source.snippet && (
                    <p className="text-muted-foreground line-clamp-2 text-xs">{source.snippet}</p>
                )}

                <div className="flex flex-row items-center gap-2">
                    {sourceType && (
                        <Badge variant="secondary" size="sm" className="text-[10px]">
                            {sourceType}
                        </Badge>
                    )}
                    {credibilityScore !== undefined && (
                        <div className={cn('flex flex-row items-center gap-1 text-[10px]', scoreColor)}>
                            <IconShield size={10} strokeWidth={2} />
                            {scoreLabel} ({(score * 100).toFixed(0)}%)
                        </div>
                    )}
                </div>
            </a>
        );
    }
);

SourceCard.displayName = 'SourceCard';

/**
 * Grid layout for multiple source cards.
 */
export const SourceCardGrid = ({
    sources,
}: {
    sources: Array<Source & { credibilityScore?: number; sourceType?: string }>;
}) => {
    if (!sources || sources.length === 0) return null;

    return (
        <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
            {sources.map((source, index) => (
                <SourceCard
                    key={`${source.link}-${index}`}
                    source={source}
                    credibilityScore={source.credibilityScore}
                    sourceType={source.sourceType}
                />
            ))}
        </div>
    );
};
