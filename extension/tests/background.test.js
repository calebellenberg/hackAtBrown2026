/**
 * Unit tests for background.js service worker.
 *
 * Tests the message handler that proxies pipeline-analyze requests
 * to the backend.
 */

// ── Simulate background.js message handler ─────────────────────────────

const BACKEND_URL = 'http://localhost:8000';

function createMessageHandler() {
  /**
   * Simulates the chrome.runtime.onMessage handler from background.js.
   * Returns a function that processes messages and calls sendResponse.
   */
  return async function handleMessage(msg, sender, sendResponse) {
    if (msg.type !== 'pipeline-analyze') {
      sendResponse({ error: 'Unknown request type' });
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/pipeline-analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.body || {}),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      sendResponse({ data });
    } catch (err) {
      sendResponse({ error: err.message || 'Could not connect to backend' });
    }
  };
}


// ════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════

describe('background.js message handler', () => {
  let handler;

  beforeEach(() => {
    handler = createMessageHandler();
    // Mock global fetch
    global.fetch = jest.fn();
  });

  afterEach(() => {
    delete global.fetch;
  });

  test('proxies pipeline-analyze to backend with correct URL and body', async () => {
    const mockData = { impulse_score: 0.5, intervention_action: 'MIRROR' };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockData),
    });

    const sendResponse = jest.fn();
    await handler(
      { type: 'pipeline-analyze', body: { product: 'Test', cost: 10 } },
      {},
      sendResponse
    );

    expect(global.fetch).toHaveBeenCalledWith(
      `${BACKEND_URL}/pipeline-analyze`,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product: 'Test', cost: 10 }),
      })
    );
    expect(sendResponse).toHaveBeenCalledWith({ data: mockData });
  });

  test('returns { data } on success', async () => {
    const mockData = {
      p_impulse_fast: 0.4,
      fast_brain_intervention: 'MIRROR',
      impulse_score: 0.45,
      intervention_action: 'MIRROR',
    };
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockData),
    });

    const sendResponse = jest.fn();
    await handler(
      { type: 'pipeline-analyze', body: {} },
      {},
      sendResponse
    );

    expect(sendResponse).toHaveBeenCalledWith({ data: mockData });
  });

  test('returns { error } on fetch failure', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'));

    const sendResponse = jest.fn();
    await handler(
      { type: 'pipeline-analyze', body: {} },
      {},
      sendResponse
    );

    expect(sendResponse).toHaveBeenCalledWith({ error: 'Network error' });
  });

  test('returns { error } on non-OK HTTP status', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    const sendResponse = jest.fn();
    await handler(
      { type: 'pipeline-analyze', body: {} },
      {},
      sendResponse
    );

    expect(sendResponse).toHaveBeenCalledWith({ error: 'HTTP 500' });
  });

  test('unknown message type returns error', async () => {
    const sendResponse = jest.fn();
    await handler(
      { type: 'unknown-type' },
      {},
      sendResponse
    );

    expect(sendResponse).toHaveBeenCalledWith({ error: 'Unknown request type' });
  });
});
