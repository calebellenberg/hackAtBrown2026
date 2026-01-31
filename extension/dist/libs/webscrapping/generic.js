import { parsePrice } from './utils/price';
export function getGenericPrice() {
    const elements = Array.from(document.querySelectorAll('span, div'));
    for (const el of elements) {
        const text = el.textContent?.trim() || '';
        if (text.match(/[$€£]\s?\d+/)) {
            const value = parsePrice(text);
            if (value && value > 0)
                return { raw: text, value };
        }
    }
    return { raw: null, value: null };
}
