
interface PriceResponse {
    price: string | null;
    value: number | null;
}

const getPriceButton = document.getElementById('get-price') as HTMLButtonElement;
const priceDisplay = document.getElementById('price') as HTMLDivElement;

getPriceButton.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
        priceDisplay.textContent = 'No active tab';
        return;
    }

    const tabId = tab.id;

    function showResult(resp: PriceResponse): void {
        const display = resp?.price ?? 'Not found';
        const value = resp?.value;
        priceDisplay.textContent = value != null ? `$${value.toFixed(2)}` : display;
    }

    chrome.tabs.sendMessage(tabId, { type: 'GET_PRICE' }, async (resp: PriceResponse) => {
        if (chrome.runtime.lastError) {
            // Try to inject the content script, then retry
            priceDisplay.textContent = 'Injecting helper script...';
            try {
                await chrome.scripting.executeScript({
                    target: { tabId: tabId },
                    files: ['dist/content.js']
                });
            } catch (err: any) {
                const msg = err?.message || (chrome.runtime.lastError && chrome.runtime.lastError.message) || 'unknown error';
                console.error('scripting.executeScript failed:', err, chrome.runtime.lastError);
                priceDisplay.textContent = `Failed to inject: ${msg}`;
                return;
            }

            // Small delay to allow content script to register its listener
            setTimeout(() => {
                chrome.tabs.sendMessage(tabId, { type: 'GET_PRICE' }, (resp2: PriceResponse) => {
                    if (chrome.runtime.lastError) {
                        const msg = chrome.runtime.lastError.message || 'Content script still not responding';
                        console.error('sendMessage after inject error:', chrome.runtime.lastError);
                        priceDisplay.textContent = msg;
                        return;
                    }
                    showResult(resp2);
                });
            }, 300);
            return;
        }
        showResult(resp);
    });
});

