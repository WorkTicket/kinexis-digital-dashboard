export {};

declare global {
  interface Window {
    kinexis?: {
      getBackendPort: () => Promise<number>;
      backendPort?: number;
      getApiToken?: () => Promise<string>;
      openExternalUrl: (url: string) => Promise<boolean>;
      openAuthWindow: (url: string) => Promise<boolean>;
      getStartupSetting: () => Promise<boolean>;
      setStartupSetting: (enabled: boolean) => Promise<boolean>;
      getVersion: () => Promise<string>;
      windowMinimize?: () => Promise<void>;
      windowMaximize?: () => Promise<boolean>;
      windowClose?: () => Promise<void>;
      windowIsMaximized?: () => Promise<boolean>;
      onWindowMaximized?: (callback: (maximized: boolean) => void) => () => void;
      onInsightNotification?: (
        callback: (data: { title?: string; body?: string; severity?: string }) => void
      ) => () => void;
      openCursorForTask?: (
        taskId: number,
        taskData: {
          title?: string;
          message?: string;
          recommendedAction?: string;
          notes?: string;
          clientName?: string;
          targetQuery?: string;
          targetUrl?: string;
          evidence?: string;
          fromToCopy?: string;
          playbookPattern?: string;
        }
      ) => Promise<{ ok: boolean; taskFile?: string; error?: string }>;
      getProjectRoot?: () => Promise<string>;
      onSignOutComplete?: (callback: () => void) => () => void;
      onBackendUnavailable?: (callback: (unavailable: boolean) => void) => () => void;
      checkForUpdates?: () => Promise<{ ok: boolean; error?: string }>;
      installUpdate?: () => Promise<boolean>;
      getUpdateStatus?: () => Promise<{ status: string }>;
      onUpdateStatus?: (
        callback: (data: {
          status: string;
          version?: string;
          percent?: number;
          message?: string;
        }) => void
      ) => () => void;
    };
  }
}
