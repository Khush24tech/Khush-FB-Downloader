/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Analytics } from '@vercel/analytics/react';

export default function App() {
  return (
    <div>
      {/* Your downloader UI will go here */}
      
      {/* Vercel Analytics Tracker */}
      <Analytics />
    </div>
  );
}