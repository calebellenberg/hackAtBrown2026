export function getSite() {
    const host = window.location.hostname || '';
    if (host.includes('amazon'))
        return 'amazon';
    if (document.querySelector('meta[name="generator"][content*="Shopify"]'))
        return 'shopify';
    return 'unknown';
}
