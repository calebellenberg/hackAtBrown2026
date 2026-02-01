/**
 * API Test Helper for Stop Shopping Extension
 * 
 * This file provides utilities to retrieve and test the saved purchase data
 * with your backend API.
 * 
 * USAGE:
 * 1. Open a shopping site where the extension is active
 * 2. Open DevTools Console (Cmd+Option+I or F12)
 * 3. Copy and paste the functions below, or import this file
 * 4. Call the functions to get/send data to your API
 */

// ==================== DATA RETRIEVAL FUNCTIONS ====================

/**
 * Get all Add to Cart history
 */
function getAddToCartHistory() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['add_to_cart_history'], (result) => {
            const data = result.add_to_cart_history || [];
            console.log('📦 Add to Cart History:', data.length, 'entries');
            console.log(JSON.stringify(data, null, 2));
            resolve(data);
        });
    });
}

/**
 * Get all Buy Now history
 */
function getBuyNowHistory() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['buy_now_history'], (result) => {
            const data = result.buy_now_history || [];
            console.log('💳 Buy Now History:', data.length, 'entries');
            console.log(JSON.stringify(data, null, 2));
            resolve(data);
        });
    });
}

/**
 * Get all purchase attempts (both Add to Cart and Buy Now)
 */
function getAllPurchaseHistory() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['all_purchase_attempts'], (result) => {
            const data = result.all_purchase_attempts || [];
            console.log('📊 All Purchase History:', data.length, 'entries');
            console.log(JSON.stringify(data, null, 2));
            resolve(data);
        });
    });
}

/**
 * Get user preferences
 */
function getUserPreferences() {
    return new Promise((resolve) => {
        const prefs = localStorage.getItem('stop_shopping_preferences');
        const data = prefs ? JSON.parse(prefs) : null;
        console.log('⚙️ User Preferences:', data);
        resolve(data);
    });
}

/**
 * Export all data as a single JSON object
 */
function exportAllData() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['add_to_cart_history', 'buy_now_history', 'all_purchase_attempts'], (result) => {
            const prefs = localStorage.getItem('stop_shopping_preferences');
            
            const exportData = {
                exportedAt: new Date().toISOString(),
                userPreferences: prefs ? JSON.parse(prefs) : null,
                addToCartHistory: result.add_to_cart_history || [],
                buyNowHistory: result.buy_now_history || [],
                allPurchaseAttempts: result.all_purchase_attempts || []
            };
            
            console.log('📤 EXPORTED DATA:');
            console.log(JSON.stringify(exportData, null, 2));
            resolve(exportData);
        });
    });
}

// ==================== API TESTING FUNCTIONS ====================

/**
 * Send purchase data to your backend API
 * @param {string} apiUrl - Your API endpoint URL
 * @param {object} data - The data to send (optional, defaults to all purchase history)
 */
async function sendToAPI(apiUrl, data = null) {
    try {
        // If no data provided, get all purchase history
        if (!data) {
            data = await new Promise((resolve) => {
                chrome.storage.local.get(['all_purchase_attempts'], (result) => {
                    resolve({
                        purchases: result.all_purchase_attempts || [],
                        sentAt: new Date().toISOString()
                    });
                });
            });
        }
        
        console.log('📤 Sending to API:', apiUrl);
        console.log('Data:', JSON.stringify(data, null, 2));
        
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        console.log('✅ API Response:', result);
        return result;
    } catch (error) {
        console.error('❌ API Error:', error);
        throw error;
    }
}

/**
 * Send a single purchase entry to API for inference/analysis
 * @param {string} apiUrl - Your API endpoint URL  
 * @param {object} purchaseEntry - Single purchase entry object
 */
async function sendSinglePurchaseToAPI(apiUrl, purchaseEntry) {
    try {
        console.log('📤 Sending single purchase to API:', apiUrl);
        console.log('Data:', JSON.stringify(purchaseEntry, null, 2));
        
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(purchaseEntry)
        });
        
        const result = await response.json();
        console.log('✅ API Response:', result);
        return result;
    } catch (error) {
        console.error('❌ API Error:', error);
        throw error;
    }
}

/**
 * Test with your backend inference engine
 * @param {string} apiUrl - Your inference API endpoint (e.g., 'http://localhost:5000/analyze')
 */
async function testInferenceAPI(apiUrl = 'http://localhost:5000/analyze') {
    const allData = await exportAllData();
    
    // Get the most recent purchase attempt for testing
    const latestPurchase = allData.allPurchaseAttempts[allData.allPurchaseAttempts.length - 1];
    
    if (!latestPurchase) {
        console.log('⚠️ No purchase attempts to test with. Click Add to Cart or Buy Now first.');
        return null;
    }
    
    // Combine with user preferences for full context
    const testPayload = {
        userPreferences: allData.userPreferences,
        purchaseAttempt: latestPurchase,
        allHistory: allData.allPurchaseAttempts
    };
    
    return sendToAPI(apiUrl, testPayload);
}

// ==================== UTILITY FUNCTIONS ====================

/**
 * Clear all saved purchase history
 */
function clearAllHistory() {
    return new Promise((resolve) => {
        chrome.storage.local.remove(['add_to_cart_history', 'buy_now_history', 'all_purchase_attempts'], () => {
            console.log('🗑️ All purchase history cleared');
            resolve(true);
        });
    });
}

/**
 * Download data as JSON file
 */
async function downloadAsJSON() {
    const data = await exportAllData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stop_shopping_data_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    console.log('📥 JSON file downloaded');
}

// ==================== SAMPLE API PAYLOAD FORMAT ====================
/*
The data sent to your API will look like this:

{
  "userPreferences": {
    "budget": 500,
    "threshold": 100,
    "sensitivity": "medium"
  },
  "purchaseAttempt": {
    "id": "add_to_cart_1706745600000_abc123def",
    "timestamp": "2026-01-31T12:00:00.000Z",
    "actionType": "add_to_cart",
    "domain": "amazon.com",
    "pageUrl": "https://www.amazon.com/product/...",
    "productName": "Product Name Here",
    "priceRaw": "$29.99",
    "priceValue": 29.99,
    "systemStartTime": "2026-01-31T11:55:00.000Z",
    "timeToCart": 45.23,
    "timeOnSite": 300.5,
    "clickCount": 25,
    "cartClickCount": 3,
    "cartClickRate": 0.6,
    "peakScrollVelocity": 1500.5,
    "navigationPathLength": 5,
    "navigationPath": [...]
  },
  "allHistory": [...]
}
*/

// Log available functions
console.log('🛍️ Stop Shopping API Test Helper Loaded');
console.log('Available functions:');
console.log('  - getAddToCartHistory()    : Get all Add to Cart entries');
console.log('  - getBuyNowHistory()       : Get all Buy Now entries');
console.log('  - getAllPurchaseHistory()  : Get all purchase attempts');
console.log('  - getUserPreferences()     : Get user preferences');
console.log('  - exportAllData()          : Export everything as JSON');
console.log('  - sendToAPI(url, data)     : Send data to your API');
console.log('  - testInferenceAPI(url)    : Test with inference backend');
console.log('  - clearAllHistory()        : Clear all saved data');
console.log('  - downloadAsJSON()         : Download data as JSON file');
