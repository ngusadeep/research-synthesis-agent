export enum ChatMode {
    Research = 'research',
    Quick = 'quick',
}

export const ChatModeConfig: Record<
    ChatMode,
    {
        webSearch: boolean;
        imageUpload: boolean;
        retry: boolean;
        isNew?: boolean;
        isAuthRequired?: boolean;
    }
> = {
    [ChatMode.Research]: {
        webSearch: true,
        imageUpload: false,
        retry: true,
        isNew: false,
        isAuthRequired: false,
    },
    [ChatMode.Quick]: {
        webSearch: false,
        imageUpload: false,
        retry: true,
        isNew: false,
        isAuthRequired: false,
    },
};

export const CHAT_MODE_CREDIT_COSTS = {
    [ChatMode.Research]: 0,
    [ChatMode.Quick]: 0,
};

export const getChatModeName = (mode: ChatMode) => {
    switch (mode) {
        case ChatMode.Research:
            return 'Research';
        case ChatMode.Quick:
            return 'Quick';
    }
};
