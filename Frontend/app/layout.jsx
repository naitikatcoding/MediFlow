import './globals.css';

export const metadata = {
  title: 'MediFlow — Multi-Facility Inventory Intelligence & Traceability',
  description: 'Forecasts demand, detects stockout and expiry risks, finds safe surplus matches, obtains dual human approvals, and verifies medicine custody with serialized QR labels.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {children}
      </body>
    </html>
  );
}

