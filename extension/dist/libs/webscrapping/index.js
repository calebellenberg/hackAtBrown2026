import { getSite } from './utils/site';
import { getAmazonPrice } from './amazon';
import { getShopifyPrice } from './shopify';
import { getGenericPrice } from './generic';
export function getPagePrice() {
    const site = getSite();
    switch (site) {
        case 'amazon':
            return getAmazonPrice();
        case 'shopify':
            return getShopifyPrice();
        default:
            return getGenericPrice();
    }
}
