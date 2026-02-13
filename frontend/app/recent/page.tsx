'use client';
import { useChatStore } from '@/store';
import {
    Badge,
    Button,
    Command,
    CommandInput,
    CommandList,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui';
import { IconAtom, IconClock, IconPlus } from '@tabler/icons-react';
import { CommandItem } from 'cmdk';
import { MoreHorizontal } from 'lucide-react';
import moment from 'moment';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type BackendReport = {
    id: string;
    query: string;
    summary: string;
    source_count: number;
    created_at: string;
};

export default function ThreadsPage() {
    const threads = useChatStore(state => state.threads);
    const updateThread = useChatStore(state => state.updateThread);
    const deleteThread = useChatStore(state => state.deleteThread);
    const switchThread = useChatStore(state => state.switchThread);
    const { push } = useRouter();
    const [editingId, setEditingId] = useState<string | null>(null);
    const [title, setTitle] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    // Backend research reports
    const [backendReports, setBackendReports] = useState<BackendReport[]>([]);
    const [isLoadingReports, setIsLoadingReports] = useState(false);

    const fetchBackendReports = useCallback(async () => {
        setIsLoadingReports(true);
        try {
            const res = await fetch(`${API_URL}/api/history?limit=50`);
            if (res.ok) {
                const data = await res.json();
                setBackendReports(data.items || []);
            }
        } catch (err) {
            console.warn('Could not fetch backend reports:', err);
        } finally {
            setIsLoadingReports(false);
        }
    }, []);

    useEffect(() => {
        fetchBackendReports();
    }, [fetchBackendReports]);

    useEffect(() => {
        if (editingId && inputRef.current) {
            inputRef.current.focus();
        }
    }, [editingId]);

    const handleEditClick = (threadId: string, threadTitle: string, e: React.MouseEvent) => {
        e.stopPropagation();
        setEditingId(threadId);
        setTitle(threadTitle);
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        setTitle(e.target.value);
    };

    const handleInputBlur = () => {
        if (editingId) {
            updateThread({
                id: editingId,
                title: title?.trim() || 'Untitled',
            });
            setEditingId(null);
        }
    };

    const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && editingId) {
            updateThread({
                id: editingId,
                title: title?.trim() || 'Untitled',
            });
            setEditingId(null);
        }
    };

    const handleDeleteThread = (threadId: string, e: React.MouseEvent) => {
        e.stopPropagation();
        deleteThread(threadId);
    };

    const handleThreadClick = (threadId: string) => {
        push(`/chat/${threadId}`);
        switchThread(threadId);
    };

    return (
        <div className="flex w-full flex-col gap-2">
            <div className="mx-auto flex w-full max-w-2xl flex-col items-start gap-2 pt-16">
                <h3 className="font-clash text-brand text-2xl font-semibold tracking-wide">
                    Chat History
                </h3>

                {/* Backend Research Reports */}
                {backendReports.length > 0 && (
                    <div className="mb-4 w-full">
                        <p className="text-muted-foreground mb-2 text-xs font-medium uppercase tracking-wider">
                            Research Reports
                        </p>
                        <div className="flex flex-col gap-2">
                            {backendReports.map(report => (
                                <div
                                    key={report.id}
                                    className="bg-tertiary hover:bg-quaternary group relative flex w-full cursor-pointer flex-col items-start rounded-md p-4 transition-all duration-200"
                                    onClick={() => push(`/chat/${report.id}`)}
                                >
                                    <div className="flex w-full flex-row items-start justify-between">
                                        <div className="flex flex-col items-start gap-1">
                                            <div className="flex flex-row items-center gap-2">
                                                <IconAtom
                                                    size={14}
                                                    strokeWidth={2}
                                                    className="text-muted-foreground"
                                                />
                                                <p className="line-clamp-2 text-sm font-medium">
                                                    {report.query}
                                                </p>
                                            </div>
                                            {report.summary && (
                                                <p className="text-muted-foreground/70 line-clamp-1 text-xs">
                                                    {report.summary}
                                                </p>
                                            )}
                                            <div className="flex flex-row items-center gap-2">
                                                <p className="text-muted-foreground/50 flex flex-row items-center gap-1 text-xs">
                                                    <IconClock size={12} strokeWidth="2" />
                                                    {moment(report.created_at).fromNow()}
                                                </p>
                                                {report.source_count > 0 && (
                                                    <Badge
                                                        variant="secondary"
                                                        size="sm"
                                                        className="text-[10px]"
                                                    >
                                                        {report.source_count} sources
                                                    </Badge>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Local Thread History */}
                <p className="text-muted-foreground text-xs font-medium uppercase tracking-wider">
                    Local Threads
                </p>
                <Command className="bg-secondary !max-h-auto w-full">
                    <CommandInput
                        placeholder="Search"
                        className="bg-tertiary h-8 w-full rounded-sm"
                    />

                    <CommandList className="bg-secondary mt-2 !max-h-none gap-2">
                        {threads?.length > 0 ? (
                            threads.map(thread => (
                                <CommandItem key={thread.id} className="mb-2">
                                    <div
                                        className="bg-tertiary hover:bg-quaternary group relative flex w-full cursor-pointer flex-col items-start rounded-md p-4 transition-all duration-200"
                                        onClick={() => handleThreadClick(thread.id)}
                                    >
                                        <div className="flex w-full justify-between">
                                            <div className="flex flex-col items-start gap-1">
                                                {editingId === thread.id ? (
                                                    <input
                                                        ref={inputRef}
                                                        value={title}
                                                        onChange={handleInputChange}
                                                        onBlur={handleInputBlur}
                                                        onKeyDown={handleInputKeyDown}
                                                        className="bg-quaternary rounded px-2 py-1 text-sm"
                                                        onClick={e => e.stopPropagation()}
                                                    />
                                                ) : (
                                                    <p className="line-clamp-2 w-full text-sm font-medium">
                                                        {thread.title}
                                                    </p>
                                                )}
                                                <p className="text-muted-foreground/50 flex flex-row items-center gap-1 text-xs">
                                                    <IconClock size={12} strokeWidth="2" />
                                                    {moment(thread.createdAt).fromNow()}
                                                </p>
                                            </div>

                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon-xs"
                                                        className="shrink-0"
                                                        onClick={e => e.stopPropagation()}
                                                    >
                                                        <MoreHorizontal
                                                            size={14}
                                                            strokeWidth="2"
                                                            className="text-muted-foreground/50"
                                                        />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end" side="right">
                                                    <DropdownMenuItem
                                                        onClick={(e: any) =>
                                                            handleEditClick(
                                                                thread.id,
                                                                thread.title,
                                                                e
                                                            )
                                                        }
                                                    >
                                                        Rename
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem
                                                        onClick={(e: any) =>
                                                            handleDeleteThread(thread.id, e)
                                                        }
                                                    >
                                                        Delete Thread
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </div>
                                    </div>
                                </CommandItem>
                            ))
                        ) : (
                            <div className="border-hard mt-2 flex w-full flex-col items-center justify-center gap-4 rounded-md border border-dashed p-4">
                                <div className="flex flex-col items-center gap-0">
                                    <p className="text-muted-foreground text-sm">
                                        No threads found
                                    </p>
                                    <p className="text-muted-foreground/70 mt-1 text-xs">
                                        Start a new conversation to create a thread
                                    </p>
                                </div>
                                <Button variant="default" size="sm" onClick={() => push('/chat')}>
                                    <IconPlus size={14} strokeWidth="2" />
                                    New Thread
                                </Button>
                            </div>
                        )}
                    </CommandList>
                </Command>
            </div>
        </div>
    );
}
