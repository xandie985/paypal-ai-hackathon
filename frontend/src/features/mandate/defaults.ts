import type { MandateInput } from '../../api/client'

export const DEFAULTS: MandateInput = {
  principal: 'ops@acme.example',
  purpose: 'Equip a 5-person engineering office',
  budget: '2200',
  auto_threshold: '300',
  per_txn_cap: '1500',
  vendor_allowlist: [
    'Northwind Displays',
    'Contoso Retail',
    'amazon.com',
    'bestbuy.com',
    'walmart.com',
    'target.com',
    'newegg.com',
    'bhphotovideo.com',
    'ebay.com',
    'adorama.com',
  ],
  allowed_categories: ['monitors', 'webcams', 'microphones'],
  min_return_days: 14,
  mode: 'auto',
}

export const PRESET_STRICT: MandateInput = {
  ...DEFAULTS,
  budget: '1200',
  auto_threshold: '0',
  per_txn_cap: '600',
  min_return_days: 30,
  mode: 'review_first',
}

