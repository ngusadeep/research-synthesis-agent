'use client';

import { ChatMode } from '@/lib/config';
import { ThreadItem } from '@/lib/types';
import { plausible } from '@/lib/helpers';
import { nanoid } from 'nanoid';
import { useParams, useRouter } from 'next/navigation';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo } from 'react';
import { useChatStore } from '@/store';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type AgentContextType = {
    runAgent: (body: any) => Promise<void>;
    handleSubmit: (args: {
        formData: FormData;
        newThreadId?: string;
        existingThreadItemId?: string;
        newChatMode?: string;
        messages?: ThreadItem[];
        useWebSearch?: boolean;
        showSuggestions?: boolean;
    }) => Promise<void>;
    updateContext: (threadId: string, data: any) => void;
};

const AgentContext = createContext<AgentContextType | undefined>(undefined);

export const AgentProvider = ({ children }: { children: ReactNode }) => {
    const { threadId: currentThreadId } = useParams();

    const {
        updateThreadItem,
        setIsGenerating,
        setAbortController,
        createThreadItem,
        setCurrentThreadItem,
        setCurrentSources,
        updateThread,
        chatMode,
        customInstructions,
    } = useChatStore(state => ({
        updateThreadItem: state.updateThreadItem,
        setIsGenerating: state.setIsGenerating,
        setAbortController: state.setAbortController,
        createThreadItem: state.createThreadItem,
        setCurrentThreadItem: state.setCurrentThreadItem,
        setCurrentSources: state.setCurrentSources,
        updateThread: state.updateThread,
        chatMode: state.chatMode,
        customInstructions: state.customInstructions,
    }));
    const { push } = useRouter();

    // In-memory store for thread items
    const threadItemMap = useMemo(() => new Map<string, ThreadItem>(), []);

    // Define common event types to reduce repetition
    const EVENT_TYPES = ['steps', 'sources', 'answer', 'error', 'status', 'suggestions'];

    // Helper: Update in-memory and store thread item
    const handleThreadItemUpdate = useCallback(
        (
            threadId: string,
            threadItemId: string,
            eventType: string,
            eventData: any,
            parentThreadItemId?: string,
            shouldPersistToDB: boolean = true
        ) => {
            const prevItem = threadItemMap.get(threadItemId) || ({} as ThreadItem);
            const updatedItem: ThreadItem = {
                ...prevItem,
                query: eventData?.query || prevItem.query || '',
                mode: eventData?.mode || prevItem.mode,
                threadId,
                parentId: parentThreadItemId || prevItem.parentId,
                id: threadItemId,
                object: eventData?.object || prevItem.object,
                createdAt: prevItem.createdAt || new Date(),
                updatedAt: new Date(),
                ...(eventType === 'answer'
                    ? {
                          answer: {
                              ...eventData.answer,
                              text: (prevItem.answer?.text || '') + eventData.answer.text,
                          },
                      }
                    : { [eventType]: eventData[eventType] }),
            };

            threadItemMap.set(threadItemId, updatedItem);
            updateThreadItem(threadId, { ...updatedItem, persistToDB: true });
        },
        [threadItemMap, updateThreadItem]
    );

    /**
     * Two-step research agent flow:
     * 1. POST /api/research to start the agent -> returns task_id
     * 2. GET /api/research/stream/{task_id} for SSE events
     */
    const runAgent = useCallback(
        async (body: any) => {
            const abortController = new AbortController();
            setAbortController(abortController);
            setIsGenerating(true);
            const startTime = performance.now();

            abortController.signal.addEventListener('abort', () => {
                setIsGenerating(false);
                updateThreadItem(body.threadId, {
                    id: body.threadItemId,
                    status: 'ABORTED',
                    persistToDB: true,
                });
            });

            try {
                // Step 1: Start the research task
                const startResponse = await fetch(`${API_URL}/api/research`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: body.prompt,
                        max_iterations: 3,
                        thread_id: body.threadId,
                    }),
                    signal: abortController.signal,
                });

                if (!startResponse.ok) {
                    const errorText = await startResponse.text();
                    setIsGenerating(false);
                    updateThreadItem(body.threadId, {
                        id: body.threadItemId,
                        status: 'ERROR',
                        error: errorText || 'Failed to start research',
                        persistToDB: true,
                    });
                    throw new Error(`HTTP error! status: ${startResponse.status}`);
                }

                const { task_id, thread_id, thread_item_id } = await startResponse.json();

                // Step 2: Connect to the SSE stream
                const eventSource = new EventSource(
                    `${API_URL}/api/research/stream/${task_id}`
                );

                const streamStartTime = performance.now();
                let eventCount = 0;
                let lastDbUpdate = Date.now();
                const DB_UPDATE_INTERVAL = 1000;

                const handleEvent = (eventType: string) => (event: MessageEvent) => {
                    eventCount++;
                    try {
                        const data = JSON.parse(event.data);
                        // Use the threadId and threadItemId from the body (local state)
                        // but merge data from the backend event
                        const threadId = body.threadId;
                        const threadItemId = body.threadItemId;

                        if (EVENT_TYPES.includes(eventType)) {
                            const shouldPersistToDB =
                                Date.now() - lastDbUpdate >= DB_UPDATE_INTERVAL;
                            handleThreadItemUpdate(
                                threadId,
                                threadItemId,
                                eventType,
                                { ...data, threadId, threadItemId },
                                undefined,
                                shouldPersistToDB
                            );
                            if (shouldPersistToDB) {
                                lastDbUpdate = Date.now();
                            }
                        }
                    } catch (err) {
                        console.warn(`JSON parse error for ${eventType}:`, err);
                    }
                };

                // Register handlers for each event type
                for (const eventType of EVENT_TYPES) {
                    eventSource.addEventListener(eventType, handleEvent(eventType));
                }

                // Handle the done event
                eventSource.addEventListener('done', (event: MessageEvent) => {
                    const streamDuration = performance.now() - streamStartTime;
                    console.log(
                        'Research completed',
                        eventCount,
                        `Stream duration: ${streamDuration.toFixed(2)}ms`
                    );

                    setIsGenerating(false);
                    threadItemMap.delete(body.threadItemId);

                    // Final persist
                    const lastItem = threadItemMap.get(body.threadItemId);
                    if (lastItem) {
                        updateThreadItem(body.threadId, {
                            ...lastItem,
                            status: 'COMPLETED',
                            persistToDB: true,
                        });
                    } else {
                        updateThreadItem(body.threadId, {
                            id: body.threadItemId,
                            status: 'COMPLETED',
                            persistToDB: true,
                        });
                    }

                    eventSource.close();
                });

                // Handle errors
                eventSource.addEventListener('error', (event: MessageEvent) => {
                    try {
                        const data = JSON.parse(event.data);
                        updateThreadItem(body.threadId, {
                            id: body.threadItemId,
                            status: 'ERROR',
                            error: data.error || 'Research agent encountered an error',
                            persistToDB: true,
                        });
                    } catch {
                        // SSE connection error (not a data event)
                    }
                    setIsGenerating(false);
                    eventSource.close();
                });

                // Handle SSE connection errors
                eventSource.onerror = () => {
                    // EventSource auto-reconnects; only close if abort was signaled
                    if (abortController.signal.aborted) {
                        eventSource.close();
                    }
                };

                // Close on abort
                abortController.signal.addEventListener('abort', () => {
                    eventSource.close();
                });

            } catch (streamError: any) {
                const totalTime = performance.now() - startTime;
                console.error('Fatal stream error:', streamError, `Total time: ${totalTime.toFixed(2)}ms`);
                setIsGenerating(false);
                if (streamError.name === 'AbortError') {
                    updateThreadItem(body.threadId, {
                        id: body.threadItemId,
                        status: 'ABORTED',
                        error: 'Generation aborted',
                    });
                } else {
                    updateThreadItem(body.threadId, {
                        id: body.threadItemId,
                        status: 'ERROR',
                        error: 'Something went wrong. Please try again.',
                    });
                }
            }
        },
        [
            setAbortController,
            setIsGenerating,
            updateThreadItem,
            handleThreadItemUpdate,
            EVENT_TYPES,
            threadItemMap,
        ]
    );

    const handleSubmit = useCallback(
        async ({
            formData,
            newThreadId,
            existingThreadItemId,
            newChatMode,
            messages,
            useWebSearch,
            showSuggestions,
        }: {
            formData: FormData;
            newThreadId?: string;
            existingThreadItemId?: string;
            newChatMode?: string;
            messages?: ThreadItem[];
            useWebSearch?: boolean;
            showSuggestions?: boolean;
        }) => {
            const mode = (newChatMode || chatMode) as ChatMode;
            const threadId = currentThreadId?.toString() || newThreadId;
            if (!threadId) return;

            // Update thread title
            updateThread({ id: threadId, title: formData.get('query') as string });

            const optimisticAiThreadItemId = existingThreadItemId || nanoid();
            const query = formData.get('query') as string;
            const imageAttachment = formData.get('imageAttachment') as string;

            const aiThreadItem: ThreadItem = {
                id: optimisticAiThreadItemId,
                createdAt: new Date(),
                updatedAt: new Date(),
                status: 'QUEUED',
                threadId,
                query,
                imageAttachment,
                mode,
            };

            createThreadItem(aiThreadItem);
            setCurrentThreadItem(aiThreadItem);
            setIsGenerating(true);
            setCurrentSources([]);

            plausible.trackEvent('send_message', {
                props: { mode },
            });

            // All modes go through the FastAPI backend
            runAgent({
                mode,
                prompt: query,
                threadId,
                threadItemId: optimisticAiThreadItemId,
                customInstructions,
                parentThreadItemId: '',
                webSearch: useWebSearch,
                showSuggestions: showSuggestions ?? true,
            });
        },
        [
            currentThreadId,
            chatMode,
            updateThread,
            createThreadItem,
            setCurrentThreadItem,
            setIsGenerating,
            setCurrentSources,
            customInstructions,
            updateThreadItem,
            runAgent,
        ]
    );

    const updateContext = useCallback(
        (threadId: string, data: any) => {
            updateThreadItem(threadId, {
                id: data.threadItemId,
                parentId: data.parentThreadItemId,
                threadId: data.threadId,
                metadata: data.context,
            });
        },
        [updateThreadItem]
    );

    const contextValue = useMemo(
        () => ({
            runAgent,
            handleSubmit,
            updateContext,
        }),
        [runAgent, handleSubmit, updateContext]
    );

    return <AgentContext.Provider value={contextValue}>{children}</AgentContext.Provider>;
};

export const useAgentStream = (): AgentContextType => {
    const context = useContext(AgentContext);
    if (!context) {
        throw new Error('useAgentStream must be used within an AgentProvider');
    }
    return context;
};
