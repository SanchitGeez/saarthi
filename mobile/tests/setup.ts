jest.mock('expo-audio', () => ({
  AudioModule: { requestRecordingPermissionsAsync: jest.fn() },
  createAudioPlayer: jest.fn(), useAudioRecorder: jest.fn(() => ({})), useAudioRecorderState: jest.fn(() => ({})),
  RecordingPresets: { HIGH_QUALITY: {} },
}));
jest.mock('expo-crypto', () => ({ randomUUID: () => 'test-request-id' }));
