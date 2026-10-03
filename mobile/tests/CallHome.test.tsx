import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { CallHome } from '../src/screens/CallHome';
import { INITIAL_CALL } from '../src/call/types';

const mockStart = jest.fn(async () => {}), mockEnd = jest.fn(async () => {}), mockMute = jest.fn();
let mockState = { ...INITIAL_CALL };
jest.mock('../src/call/useVoiceSession', () => ({ useVoiceSession: () => ({ state: mockState, start: mockStart, end: mockEnd, mute: mockMute }) }));
jest.mock('../src/api', () => ({
  getConversations: jest.fn(async () => []), getCallStatus: jest.fn(async () => ({ available: true })),
  createConversation: jest.fn(async () => ({ id:'chat-1', title:'A new conversation', private:false })),
  deleteConversation: jest.fn(async () => {}),
}));
jest.mock('../src/screens/ChatHome', () => ({ ChatHome: ({ initialConversationId }: { initialConversationId: string }) => {
  const { Text } = require('react-native'); return <Text>Typed chat: {initialConversationId}</Text>;
} }));
jest.mock('../src/screens/MemorySettings', () => ({ MemorySettings: () => null }));
const user = { id:'user-1', email:'user@example.com', memory_enabled:true, language:'hinglish' as const };
function home() { return render(<SafeAreaProvider initialMetrics={{ frame: { x:0,y:0,width:390,height:844 }, insets:{ top:0,bottom:0,left:0,right:0 } }}><CallHome user={user} onSignOut={jest.fn()} onUserChange={jest.fn()} /></SafeAreaProvider>); }
beforeEach(() => { jest.clearAllMocks(); mockState = { ...INITIAL_CALL }; });
test('quiet temple exposes the two start choices and no topic grid', async () => {
  await home(); await waitFor(() => expect(screen.getByText(/Parth · AI/)).toBeTruthy());
  expect(screen.getByLabelText('Baat karein, start a live conversation')).toBeTruthy(); expect(screen.getByLabelText('Type to Parth')).toBeTruthy();
  expect(screen.queryByText('Relationships')).toBeNull(); expect(mockStart).not.toHaveBeenCalled();
});
test('explicit start creates conversation and starts voice once', async () => {
  await home(); await fireEvent.press(screen.getByLabelText('Baat karein, start a live conversation'));
  await waitFor(() => expect(mockStart).toHaveBeenCalledWith('chat-1','test-request-id'));
});
test('Type opens text without starting microphone or calling the agent', async () => {
  await home(); await fireEvent.press(screen.getByLabelText('Type to Parth'));
  await waitFor(() => expect(screen.getByText('Typed chat:')).toBeTruthy()); expect(mockStart).not.toHaveBeenCalled();
});
test('speaking state shows caption and call controls, captions can hide', async () => {
  mockState = { ...INITIAL_CALL, phase:'speaking', lit:true, caption:'Parth: How are you today?' };
  await home(); expect(screen.getByText('Parth is speaking')).toBeTruthy();
  expect(screen.getByText('Parth: How are you today?')).toBeTruthy(); await fireEvent.press(screen.getByLabelText('Hide captions'));
  expect(screen.queryByText('Parth: How are you today?')).toBeNull(); await fireEvent.press(screen.getByLabelText('Mute microphone')); expect(mockMute).toHaveBeenCalled();
  await fireEvent.press(screen.getByLabelText('End call')); expect(mockEnd).toHaveBeenCalled();
});
test('unconfigured calls show error and keep Type available', async () => {
  const { getCallStatus } = require('../src/api'); getCallStatus.mockResolvedValueOnce({ available:false }).mockResolvedValueOnce({ available:false });
  await home(); await waitFor(() => expect(screen.getByText('Live calls coming soon · Type is ready')).toBeTruthy());
  await fireEvent.press(screen.getByLabelText('Baat karein, start a live conversation'));
  await waitFor(() => expect(screen.getByText('Live calls aren’t ready yet. You can still type to Parth.')).toBeTruthy()); expect(mockStart).not.toHaveBeenCalled();
});
