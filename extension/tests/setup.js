/**
 * Chrome API mock layer for Jest tests.
 *
 * Provides stubs for chrome.runtime, chrome.storage.local, and other
 * browser extension APIs needed by content.js, tracker.js, popup.js,
 * and background.js.
 */

// In-memory storage backend for chrome.storage.local
const _storageData = {};

const chromeStorageLocal = {
  get: jest.fn((keys, callback) => {
    const result = {};
    if (typeof keys === 'string') {
      result[keys] = _storageData[keys];
    } else if (Array.isArray(keys)) {
      keys.forEach(k => { result[k] = _storageData[k]; });
    } else if (keys && typeof keys === 'object') {
      Object.keys(keys).forEach(k => {
        result[k] = _storageData[k] !== undefined ? _storageData[k] : keys[k];
      });
    } else {
      Object.assign(result, _storageData);
    }
    if (callback) setTimeout(() => callback(result), 0);
  }),
  set: jest.fn((items, callback) => {
    Object.assign(_storageData, items);
    if (callback) setTimeout(() => callback(), 0);
  }),
  remove: jest.fn((keys, callback) => {
    if (typeof keys === 'string') {
      delete _storageData[keys];
    } else if (Array.isArray(keys)) {
      keys.forEach(k => delete _storageData[k]);
    }
    if (callback) setTimeout(() => callback(), 0);
  }),
  clear: jest.fn((callback) => {
    Object.keys(_storageData).forEach(k => delete _storageData[k]);
    if (callback) setTimeout(() => callback(), 0);
  }),
};

// Mock chrome object
global.chrome = {
  runtime: {
    getURL: jest.fn((path) => `chrome-extension://mock-extension-id/${path}`),
    sendMessage: jest.fn((msg, callback) => {
      if (callback) setTimeout(() => callback({}), 0);
    }),
    onMessage: {
      addListener: jest.fn(),
    },
  },
  storage: {
    local: chromeStorageLocal,
  },
};

// Helper to reset storage between tests
global.__resetChromeStorage = () => {
  Object.keys(_storageData).forEach(k => delete _storageData[k]);
  chromeStorageLocal.get.mockClear();
  chromeStorageLocal.set.mockClear();
  chromeStorageLocal.remove.mockClear();
  chromeStorageLocal.clear.mockClear();
};

// Helper to seed storage
global.__seedChromeStorage = (data) => {
  Object.assign(_storageData, data);
};

// Helper to read storage directly (for assertions)
global.__getChromeStorage = () => ({ ..._storageData });

// Mock sessionStorage (jsdom provides one but let's ensure it's clean)
beforeEach(() => {
  sessionStorage.clear();
  global.__resetChromeStorage();
});

// Mock performance.now if not available
if (typeof performance === 'undefined') {
  global.performance = { now: () => Date.now() };
}

// Suppress console.log/warn in tests for cleaner output
// Uncomment if desired:
// jest.spyOn(console, 'log').mockImplementation(() => {});
// jest.spyOn(console, 'warn').mockImplementation(() => {});
